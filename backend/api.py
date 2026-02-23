# backend/api.py
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import re
import sys
import os
import time
import json

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scraper.vlr_scraper import VLRScraper
from scraper.rib_scraper import RibScraper
from scraper.player_processor import PlayerProcessor
from scraper.prizepicks_processor import PrizePicksProcessor
from scraper.prizepicks_api import fetch_valorant_projections
from scraper.team_scraper import TeamScraper
from scraper.team_processor import TeamProcessor
from backend.database import Database
from backend.model_params import get_player_distribution, compute_distribution_params
from backend.prop_prob import compute_prop_probabilities, generate_pmf
from backend.market_implied import compute_market_parameters
from backend.odds_utils import expected_value_per_1
from backend.matchup_adjust import infer_team_win_probability, apply_matchup_adjustment
from config import Config
import logging

app = Flask(__name__, static_folder='../frontend', template_folder='../frontend/templates')
CORS(app)

# Initialize logging first
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def _parse_matchup_inputs(args):
    """Parse optional matchup inputs from request args."""
    try:
        team_win_prob = args.get('team_win_prob', None)
        team_odds = args.get('team_odds', None)
        opp_odds = args.get('opp_odds', None)

        twp = float(team_win_prob) if team_win_prob not in (None, '') else None
        to = float(team_odds) if team_odds not in (None, '') else None
        oo = float(opp_odds) if opp_odds not in (None, '') else None
        parsed = infer_team_win_probability(team_win_prob=twp, team_odds=to, opp_odds=oo)
        parsed['invalid_error'] = None
        return parsed
    except ValueError as e:
        return {
            'provided': False,
            'team_win_prob': None,
            'method': 'invalid',
            'invalid_error': str(e)
        }

# Initialize components
db = Database(Config.DATABASE_PATH)
scraper = VLRScraper(database=db)        # Used for team analysis, KPR analysis, moneylines
pp_scraper = RibScraper(database=db)     # Used for PrizePicks leaderboard (rib.gg doesn't IP-ban)
team_scraper = TeamScraper(database=db)

# Add request logging middleware (after logger is initialized)
@app.before_request
def log_request_info():
    print(f">>> {request.method} {request.path}", flush=True)
    logger.info(f"REQUEST: {request.method} {request.path}")
    if request.args:
        logger.info(f"Query params: {request.args}")

@app.after_request
def log_response_info(response):
    logger.info(f"RESPONSE: {response.status_code} for {request.path}")
    return response

# Add error handler for 404 to debug (must be after routes are defined)


@app.route('/api/health')
def health():
    """Quick health check - if you see '>>> GET /api/health' in terminal, server is receiving requests."""
    return jsonify({'ok': True, 'message': 'Server is running'})

@app.route('/')
def index():
    """Serve the frontend"""
    return send_from_directory('../frontend/templates', 'index.html')

@app.route('/challengers')
def challengers_page():
    """Challengers player analysis page"""
    return send_from_directory('../frontend/templates', 'challengers.html')

@app.route('/challengers/prizepicks')
def challengers_prizepicks_page():
    """Challengers PrizePicks page"""
    return send_from_directory('../frontend/templates', 'challengers-prizepicks.html')

@app.route('/api/player/<ign>', methods=['GET'])
def get_player_analysis(ign):
    """Get KPR analysis for a specific player"""
    try:
        # Get kill line from query params or use default (e.g., 15.5 kills)
        kill_line = float(request.args.get('line', Config.DEFAULT_KILL_LINE))
        
        # Create processor with specified kill line
        processor = PlayerProcessor(kill_line=kill_line)
        
        logger.info(f"Scraping data for player: {ign} with kill line: {kill_line}")
        
        # Scrape fresh data from VLR.gg (pass kill_line for over/under calculation)
        player_data = scraper.get_player_by_ign(ign, kill_line=kill_line)
        
        if not player_data:
            return jsonify({'error': 'Player not found'}), 404
        
        # Save to database
        player_id = db.save_player_data(player_data)
        
        # Perform analysis
        analysis = processor.evaluate_betting_line(player_data)

        matchup = _parse_matchup_inputs(request.args)
        if matchup.get('invalid_error'):
            return jsonify({'error': matchup['invalid_error']}), 400
        if matchup.get('provided') and player_data.get('all_map_kills'):
            dist_params = compute_distribution_params(player_data['all_map_kills'])
            adj = apply_matchup_adjustment(dist_params, matchup['team_win_prob'])
            adjusted_probs = compute_prop_probabilities(adj['dist_params'], kill_line)
            analysis['matchup_adjusted_probabilities'] = {
                'p_over': adjusted_probs['p_over'],
                'p_under': adjusted_probs['p_under'],
                'team_win_prob': matchup['team_win_prob'],
                'mu_base': adj.get('mu_base'),
                'mu_adjusted': adj.get('mu_adjusted'),
                'multiplier': adj.get('multiplier'),
                'components': adj.get('components', {}),
                'input_method': matchup.get('method')
            }
        
        # Add agent and map aggregations
        agent_stats = db.get_player_agent_aggregation(ign)
        map_stats = db.get_player_map_aggregation(ign)
        
        # Return response
        return jsonify({
            'success': True,
            'analysis': analysis,
            'agent_stats': agent_stats,
            'map_stats': map_stats,
            'player_info': {
                'ign': player_data['ign'],
                'team': player_data.get('team', 'Unknown'),
                'events_count': len(player_data.get('events', []))
            },
            'raw_events': player_data.get('events', [])[:5]  # Include last 5 events for debugging
        })
        
    except Exception as e:
        logger.error(f"Error processing player {ign}: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/batch', methods=['POST'])
def batch_analysis():
    """Analyze multiple players at once"""
    try:
        data = request.json
        players = data.get('players', [])
        kill_line = float(data.get('line', Config.DEFAULT_KILL_LINE))
        
        results = []
        processor = PlayerProcessor(kill_line=kill_line)
        
        for ign in players:
            try:
                player_data = scraper.get_player_by_ign(ign, kill_line=kill_line)
                if player_data:
                    analysis = processor.evaluate_betting_line(player_data)
                    db.save_player_data(player_data)
                    results.append(analysis)
                else:
                    results.append({'ign': ign, 'error': 'Not found'})
            except Exception as e:
                results.append({'ign': ign, 'error': str(e)})
        
        return jsonify({'results': results})
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ==================== Challengers (Tier 2) API ====================

@app.route('/api/challengers/player/<ign>', methods=['GET'])
def get_challengers_player_analysis(ign):
    """Get KPR analysis for a Challengers player (tier 2, database only)"""
    try:
        kill_line = float(request.args.get('line', Config.DEFAULT_KILL_LINE))
        processor = PlayerProcessor(kill_line=kill_line)
        player_data = scraper.get_player_challengers_data(ign, kill_line=kill_line)
        if not player_data or not player_data.get('ign'):
            return jsonify({'error': 'Player not found or no Challengers data'}), 404
        analysis = processor.evaluate_betting_line(player_data)
        matchup = _parse_matchup_inputs(request.args)
        if matchup.get('invalid_error'):
            return jsonify({'error': matchup['invalid_error']}), 400
        if matchup.get('provided') and player_data.get('all_map_kills'):
            dist_params = compute_distribution_params(player_data['all_map_kills'])
            adj = apply_matchup_adjustment(dist_params, matchup['team_win_prob'])
            adjusted_probs = compute_prop_probabilities(adj['dist_params'], kill_line)
            analysis['matchup_adjusted_probabilities'] = {
                'p_over': adjusted_probs['p_over'],
                'p_under': adjusted_probs['p_under'],
                'team_win_prob': matchup['team_win_prob'],
                'mu_base': adj.get('mu_base'),
                'mu_adjusted': adj.get('mu_adjusted'),
                'multiplier': adj.get('multiplier'),
                'components': adj.get('components', {}),
                'input_method': matchup.get('method')
            }
        agent_stats = db.get_player_agent_aggregation(ign, tier=2)
        map_stats = db.get_player_map_aggregation(ign, tier=2)
        return jsonify({
            'success': True,
            'analysis': analysis,
            'agent_stats': agent_stats,
            'map_stats': map_stats,
            'player_info': {
                'ign': player_data['ign'],
                'team': player_data.get('team', 'Unknown'),
                'events_count': len(player_data.get('events', []))
            },
            'raw_events': player_data.get('events', [])[:5]
        })
    except Exception as e:
        logger.error(f"Error processing Challengers player {ign}: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/challengers/edge/<ign>', methods=['GET'])
def get_challengers_edge_analysis(ign):
    """Mathematical edge analysis for Challengers player"""
    try:
        line = float(request.args.get('line', 18.5))
        over_odds = float(request.args.get('over_odds', -110))
        under_odds = float(request.args.get('under_odds', -110))
        matchup = _parse_matchup_inputs(request.args)
        if matchup.get('invalid_error'):
            return jsonify({'error': matchup['invalid_error']}), 400
        player_data = scraper.get_player_challengers_data(ign, kill_line=line)
        if not player_data or not player_data.get('all_map_kills'):
            return jsonify({'error': 'Player not found or insufficient Challengers data'}), 404
        all_map_kills = player_data['all_map_kills']
        if len(all_map_kills) < 5:
            return jsonify({'error': f'Insufficient data ({len(all_map_kills)} maps)'}), 400
        dist_params = compute_distribution_params(all_map_kills)
        adj = apply_matchup_adjustment(dist_params, matchup.get('team_win_prob'))
        dist_for_probs = adj['dist_params']
        model_probs = compute_prop_probabilities(dist_for_probs, line)
        market_params = compute_market_parameters(
            line=line, over_odds=over_odds, under_odds=under_odds,
            model_dist_type=dist_for_probs['dist'], model_dispersion=dist_for_probs.get('k'))
        p_over_model = model_probs['p_over']
        p_under_model = model_probs['p_under']
        p_over_market = market_params['p_over_vigfree']
        p_under_market = market_params['p_under_vigfree']
        prob_edge_over = p_over_model - p_over_market
        prob_edge_under = p_under_model - p_under_market
        ev_over = expected_value_per_1(p_over_model, over_odds)
        ev_under = expected_value_per_1(p_under_model, under_odds)
        recommended = 'OVER' if (ev_over > 0 and ev_over >= ev_under) else ('UNDER' if ev_under > 0 else 'NO BET')
        best_ev = max(ev_over, ev_under)
        mu = dist_for_probs['mu']
        var = dist_for_probs.get('var', 0)
        model_pmf = generate_pmf(dist_for_probs, (max(0, int(mu - 15)), int(mu + 15)))
        market_dist_params = {'dist': dist_for_probs['dist'], 'mu': market_params['mu_market'], 'lambda': market_params['mu_market']}
        if dist_for_probs['dist'] == 'nbinom':
            k = dist_for_probs.get('k', 1.0)
            market_dist_params['k'] = k
            market_dist_params['p'] = k / (k + market_params['mu_market'])
        market_pmf = generate_pmf(market_dist_params, (max(0, int(mu - 15)), int(mu + 15)))
        return jsonify({
            'success': True,
            'scope': 'challengers',
            'player': {'ign': player_data['ign'], 'sample_size': len(all_map_kills), 'confidence': dist_params.get('confidence', '')},
            'line': line,
            'model': {'dist': dist_for_probs['dist'], 'mu': mu, 'var': var, 'p_over': p_over_model, 'p_under': p_under_model},
            'market': {
                'over_odds': over_odds, 'under_odds': under_odds,
                'p_over_vigfree': p_over_market, 'p_under_vigfree': p_under_market,
                'vig_percentage': market_params.get('vig_percentage', 0),
                'mu_implied': market_params.get('mu_market', mu)
            },
            'matchup_adjustment': {
                'applied': adj.get('applied', False),
                'team_win_prob': matchup.get('team_win_prob'),
                'input_method': matchup.get('method'),
                'mu_base': adj.get('mu_base'),
                'mu_adjusted': adj.get('mu_adjusted'),
                'multiplier': adj.get('multiplier'),
                'components': adj.get('components', {})
            },
            'edge': {
                'prob_edge_over': prob_edge_over, 'prob_edge_under': prob_edge_under,
                'ev_over': ev_over, 'ev_under': ev_under,
                'recommended': recommended, 'best_ev': best_ev,
                'roi_over_pct': ev_over * 100, 'roi_under_pct': ev_under * 100
            },
            'visualization': {
                'x': model_pmf['x'], 'model_pmf': model_pmf['pmf'],
                'market_pmf': market_pmf['pmf'], 'line_position': line
            }
        })
    except Exception as e:
        logger.error(f"Error in Challengers edge analysis for {ign}: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/api/challengers/prizepicks/<ign>', methods=['GET'])
def get_challengers_prizepicks_analysis(ign):
    """PrizePicks analysis for Challengers player"""
    try:
        kill_line = float(request.args.get('line', 30.5))
        combo_maps = int(request.args.get('combo_maps', 2))
        combo_maps = 2 if combo_maps not in (2, 3) else combo_maps
        processor = PrizePicksProcessor(kill_line=kill_line, combo_maps=combo_maps)
        player_data = pp_scraper.get_player_prizepicks_data_challengers(ign, kill_line=kill_line)
        if not player_data or not player_data.get('ign'):
            return jsonify({'error': 'Player not found or no Challengers data'}), 404
        analysis = processor.evaluate_prizepicks_line(player_data)
        matchup = _parse_matchup_inputs(request.args)
        if matchup.get('invalid_error'):
            return jsonify({'error': matchup['invalid_error']}), 400
        if matchup.get('provided'):
            combo_samples = []
            for match_data in player_data.get('match_combinations', []):
                map_kills = [k for k in match_data.get('map_kills', []) if k is not None and k > 0]
                if len(map_kills) < 2:
                    continue
                combos = processor.process_match_combinations(map_kills)
                combo_samples.extend([c['combined_kills'] for c in combos])
            if len(combo_samples) >= 3:
                dist_params = compute_distribution_params(combo_samples)
                adj = apply_matchup_adjustment(dist_params, matchup['team_win_prob'])
                adjusted_probs = compute_prop_probabilities(adj['dist_params'], kill_line)
                analysis['matchup_adjusted_probabilities'] = {
                    'p_over': adjusted_probs['p_over'],
                    'p_under': adjusted_probs['p_under'],
                    'team_win_prob': matchup['team_win_prob'],
                    'mu_base': adj.get('mu_base'),
                    'mu_adjusted': adj.get('mu_adjusted'),
                    'multiplier': adj.get('multiplier'),
                    'components': adj.get('components', {}),
                    'input_method': matchup.get('method')
                }
        return jsonify({
            'success': True,
            'analysis': analysis,
            'player_info': {
                'ign': player_data['ign'],
                'team': player_data.get('team', 'Unknown'),
                'matches_count': len(player_data.get('match_combinations', []))
            }
        })
    except Exception as e:
        logger.error(f"Error processing Challengers PrizePicks for {ign}: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/api/challengers/prizepicks/edge/<ign>', methods=['GET'])
def get_challengers_prizepicks_edge(ign):
    """PrizePicks edge analysis for Challengers player"""
    try:
        line = float(request.args.get('line', 30.5))
        combo_maps = int(request.args.get('combo_maps', 2))
        combo_maps = 2 if combo_maps not in (2, 3) else combo_maps
        over_odds = float(request.args.get('over_odds', -110))
        under_odds = float(request.args.get('under_odds', -110))
        matchup = _parse_matchup_inputs(request.args)
        if matchup.get('invalid_error'):
            return jsonify({'error': matchup['invalid_error']}), 400
        player_data = pp_scraper.get_player_prizepicks_data_challengers(ign, kill_line=line)
        if not player_data or not player_data.get('ign'):
            return jsonify({'error': 'Player not found'}), 404
        pp_processor = PrizePicksProcessor(kill_line=line, combo_maps=combo_maps)
        combo_samples = db.get_cached_combo_samples_challengers(ign, combo_maps=combo_maps)
        if combo_samples is None:
            combo_samples = []
            for match_data in player_data.get('match_combinations', []):
                map_kills = [k for k in match_data.get('map_kills', []) if k is not None and k > 0]
                if len(map_kills) < 2:
                    continue
                combos = pp_processor.process_match_combinations(map_kills)
                combo_samples.extend([c['combined_kills'] for c in combos])
            if combo_samples:
                db.save_combo_cache_challengers(ign, combo_samples, combo_maps=combo_maps)
        if len(combo_samples) < 3:
            return jsonify({'error': f'Insufficient {combo_maps}-map combo samples'}), 400
        dist_params = compute_distribution_params(combo_samples)
        adj = apply_matchup_adjustment(dist_params, matchup.get('team_win_prob'))
        dist_for_probs = adj['dist_params']
        model_probs = compute_prop_probabilities(dist_for_probs, line)
        market_params = compute_market_parameters(
            line=line, over_odds=over_odds, under_odds=under_odds,
            model_dist_type=dist_for_probs['dist'], model_dispersion=dist_for_probs.get('k'))
        p_over_model = model_probs['p_over']
        p_under_model = model_probs['p_under']
        p_over_market = market_params['p_over_vigfree']
        p_under_market = market_params['p_under_vigfree']
        ev_over = expected_value_per_1(p_over_model, over_odds)
        ev_under = expected_value_per_1(p_under_model, under_odds)
        recommended = 'OVER' if (ev_over > 0 and ev_over >= ev_under) else ('UNDER' if ev_under > 0 else 'NO BET')
        prob_edge_over = p_over_model - p_over_market
        prob_edge_under = p_under_model - p_under_market
        mu = dist_for_probs['mu']
        var = dist_for_probs.get('var', 0)
        model_pmf = generate_pmf(dist_for_probs, (max(0, int(mu - 25)), int(mu + 25)))
        market_dist_params = {'dist': dist_for_probs['dist'], 'mu': market_params['mu_market'], 'lambda': market_params['mu_market']}
        if dist_for_probs['dist'] == 'nbinom':
            k = dist_for_probs.get('k', 1.0)
            market_dist_params['k'] = k
            market_dist_params['p'] = k / (k + market_params['mu_market'])
        market_pmf = generate_pmf(market_dist_params, (max(0, int(mu - 25)), int(mu + 25)))
        return jsonify({
            'success': True,
            'scope': 'challengers_prizepicks',
            'player': {'ign': player_data['ign'], 'sample_size': len(combo_samples)},
            'line': line,
            'model': {'dist': dist_for_probs['dist'], 'mu': mu, 'var': var, 'p_over': p_over_model, 'p_under': p_under_model},
            'market': {
                'over_odds': over_odds, 'under_odds': under_odds,
                'p_over_vigfree': p_over_market, 'p_under_vigfree': p_under_market,
                'mu_implied': market_params.get('mu_market', mu)
            },
            'matchup_adjustment': {
                'applied': adj.get('applied', False),
                'team_win_prob': matchup.get('team_win_prob'),
                'input_method': matchup.get('method'),
                'mu_base': adj.get('mu_base'),
                'mu_adjusted': adj.get('mu_adjusted'),
                'multiplier': adj.get('multiplier'),
                'components': adj.get('components', {})
            },
            'edge': {
                'prob_edge_over': prob_edge_over, 'prob_edge_under': prob_edge_under,
                'ev_over': ev_over, 'ev_under': ev_under,
                'recommended': recommended,
                'roi_over_pct': ev_over * 100, 'roi_under_pct': ev_under * 100
            },
            'visualization': {
                'x': model_pmf['x'], 'model_pmf': model_pmf['pmf'],
                'market_pmf': market_pmf['pmf'], 'line_position': line
            }
        })
    except Exception as e:
        logger.error(f"Error in Challengers PrizePicks edge for {ign}: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/api/edge/<ign>', methods=['GET'])
def get_edge_analysis(ign):
    """
    Get mathematical edge analysis with odds.
    
    Query params:
        line: Kill line (e.g., 18.5)
        over_odds: American odds for Over (e.g., -110)
        under_odds: American odds for Under (e.g., -110)
        last_n: Optional - use last N maps (default: all available)
    """
    try:
        # Get parameters
        line = float(request.args.get('line', 18.5))
        over_odds = float(request.args.get('over_odds', -110))
        under_odds = float(request.args.get('under_odds', -110))
        last_n = request.args.get('last_n', None)
        
        if last_n:
            last_n = int(last_n)
        
        matchup = _parse_matchup_inputs(request.args)
        if matchup.get('invalid_error'):
            return jsonify({'error': matchup['invalid_error']}), 400

        logger.info(f"Edge analysis for {ign}: line={line}, over={over_odds}, under={under_odds}, matchup={matchup.get('team_win_prob')}")
        
        # Step 1: Get player's distribution from cached data
        context = {'last_n': last_n} if last_n else {}
        dist_params = get_player_distribution(db, ign, context=context)
        
        if 'error' in dist_params:
            return jsonify({'error': dist_params['error']}), 404
        
        # Step 2: Apply optional matchup adjustment and compute model probabilities
        adj = apply_matchup_adjustment(dist_params, matchup.get('team_win_prob'))
        dist_for_probs = adj['dist_params']
        model_probs = compute_prop_probabilities(dist_for_probs, line)
        
        # Step 3: Compute market-implied parameters
        market_params = compute_market_parameters(
            line=line,
            over_odds=over_odds,
            under_odds=under_odds,
            model_dist_type=dist_for_probs['dist'],
            model_dispersion=dist_for_probs.get('k', None)
        )
        
        # Step 4: Compute edge and EV
        p_over_model = model_probs['p_over']
        p_under_model = model_probs['p_under']
        p_over_market = market_params['p_over_vigfree']
        p_under_market = market_params['p_under_vigfree']
        
        prob_edge_over = p_over_model - p_over_market
        prob_edge_under = p_under_model - p_under_market
        
        ev_over = expected_value_per_1(p_over_model, over_odds)
        ev_under = expected_value_per_1(p_under_model, under_odds)
        
        # Step 5: Determine recommendation
        if ev_over > 0 and ev_over > ev_under:
            recommended = 'OVER'
            best_ev = ev_over
        elif ev_under > 0 and ev_under > ev_over:
            recommended = 'UNDER'
            best_ev = ev_under
        else:
            recommended = 'NO BET'
            best_ev = max(ev_over, ev_under)
        
        # Step 6: Generate PMF for visualization
        mu = dist_for_probs['mu']
        x_min = max(0, int(mu - 15))
        x_max = int(mu + 15)
        model_pmf = generate_pmf(dist_for_probs, (x_min, x_max))
        
        # Generate market PMF (using market-implied params)
        market_dist_params = {
            'dist': dist_for_probs['dist'],
            'mu': market_params['mu_market'],
            'lambda': market_params['mu_market'],  # for Poisson
        }
        if dist_for_probs['dist'] == 'nbinom':
            # Use same dispersion as model for market PMF
            market_dist_params['k'] = dist_for_probs.get('k', 1.0)
            k = dist_for_probs.get('k', 1.0)
            market_dist_params['p'] = k / (k + market_params['mu_market'])
        
        market_pmf = generate_pmf(market_dist_params, (x_min, x_max))
        
        # Build response
        response = {
            'success': True,
            'player': {
                'ign': ign,
                'sample_size': dist_params['sample_size'],
                'confidence': dist_params['confidence']
            },
            'line': line,
            'model': {
                'dist': dist_for_probs['dist'],
                'mu': dist_for_probs['mu'],
                'var': dist_for_probs['var'],
                'p_over': p_over_model,
                'p_under': p_under_model,
                'samples': dist_params.get('samples', [])[:20]  # First 20 for debugging
            },
            'matchup_adjustment': {
                'applied': adj.get('applied', False),
                'team_win_prob': matchup.get('team_win_prob'),
                'input_method': matchup.get('method'),
                'mu_base': adj.get('mu_base'),
                'mu_adjusted': adj.get('mu_adjusted'),
                'multiplier': adj.get('multiplier'),
                'components': adj.get('components', {})
            },
            'market': {
                'over_odds': over_odds,
                'under_odds': under_odds,
                'p_over_vigfree': p_over_market,
                'p_under_vigfree': p_under_market,
                'vig_percentage': market_params['vig_percentage'],
                'mu_implied': market_params['mu_market']
            },
            'edge': {
                'prob_edge_over': prob_edge_over,
                'prob_edge_under': prob_edge_under,
                'ev_over': ev_over,
                'ev_under': ev_under,
                'recommended': recommended,
                'best_ev': best_ev,
                'roi_over_pct': ev_over * 100,
                'roi_under_pct': ev_under * 100
            },
            'visualization': {
                'x': model_pmf['x'],
                'model_pmf': model_pmf['pmf'],
                'market_pmf': market_pmf['pmf'],
                'line_position': line
            }
        }
        
        return jsonify(response)
        
    except Exception as e:
        logger.error(f"Error in edge analysis for {ign}: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/api/stats', methods=['GET'])
def get_system_stats():
    """Get system statistics"""
    try:
        stats = db.get_stats()
        return jsonify(stats)
    except Exception as e:
        logger.error(f"Error getting stats: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/cache/status', methods=['GET'])
def get_cache_status():
    """Get cache status - shows which events are cached"""
    try:
        stats = db.get_stats()
        completed_events = db.get_completed_events()
        return jsonify({
            'cache_stats': stats,
            'cached_events': [{'name': e['event_name'], 'url': e['event_url']} for e in completed_events],
            'scraper_has_db': scraper.db is not None,
            'db_path': db.db_path
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/cache/prizepicks/clear', methods=['POST'])
def clear_prizepicks_cache():
    """Clear PrizePicks player/combo caches so fresh 2026 data is fetched on next upload."""
    try:
        challengers_only = request.json.get('challengers_only', False) if request.is_json else False
        counts = db.clear_prizepicks_cache(challengers_only=challengers_only)
        return jsonify({'success': True, 'cleared': counts})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/moneylines')
def moneylines_page():
    """Serve the MoneyLine strategy page"""
    return send_from_directory('../frontend/templates', 'moneylines.html')

@app.route('/api/moneylines/stats', methods=['GET'])
def get_moneylines_stats():
    """Get moneyline strategy statistics (heavy/moderate/even favorite win rates)"""
    try:
        stats = db.get_moneyline_stats()
        return jsonify({'success': True, **stats})
    except Exception as e:
        logger.error(f"Error getting moneyline stats: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@app.route('/api/moneylines/strategy', methods=['GET'])
def get_moneylines_strategy():
    """Get full strategy data (walk-forward, bet log, consistency check, etc.)"""
    try:
        from scripts.moneyline_analytics import get_strategy_data
        data = get_strategy_data()
        if data is None:
            return jsonify({'success': False, 'message': 'No moneyline data. Run: python scripts/populate_moneyline.py'}), 404
        return jsonify(data)
    except Exception as e:
        logger.error(f"Error getting strategy data: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/moneylines/upcoming', methods=['GET'])
def get_moneylines_upcoming():
    """Scrape VLR for upcoming Americas+China matches, fetch Thunderpick odds, run strategy."""
    try:
        from scripts.moneyline_analytics import get_upcoming_picks
        data = get_upcoming_picks()
        return jsonify(data)
    except Exception as e:
        logger.error(f"Error getting upcoming picks: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e), 'picks': []}), 500

@app.route('/api/match/odds', methods=['GET'])
def get_match_odds():
    """
    Scrape Thunderpick pre-match odds from a VLR match page.
    Query param: match_path - VLR match path (e.g. /596427/mibr-vs-nrg-vct-2026-americas-kickoff-lbf)
    """
    try:
        match_path = request.args.get('match_path', '').strip()
        if not match_path:
            return jsonify({'error': 'match_path required (e.g. /596427/mibr-vs-nrg-vct-2026-americas-kickoff-lbf)'}), 400
        if not match_path.startswith('/'):
            match_path = '/' + match_path
        odds = scraper.get_match_betting_odds(match_path)
        if not odds:
            return jsonify({'success': False, 'message': 'No Thunderpick odds found for this match'}), 404
        return jsonify({'success': True, **odds})
    except Exception as e:
        logger.error(f"Error fetching match odds: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/team')
def team_page():
    """Serve the team analysis page"""
    return send_from_directory('../frontend/templates', 'team.html')

@app.route('/prizepicks')
def prizepicks_page():
    """Serve the PrizePicks analysis page"""
    return send_from_directory('../frontend/templates', 'prizepicks.html')

@app.route('/edge')
def edge_page():
    """Serve the mathematical edge analysis page"""
    return send_from_directory('../frontend/templates', 'edge.html')

@app.route('/api/team/<team_name>', methods=['GET'])
def get_team_analysis(team_name):
    """Get team analysis for a specific team"""
    try:
        region = request.args.get('region', None)  # Optional region filter
        
        logger.info(f"=" * 60)
        logger.info(f"API REQUEST: Scraping data for team: {team_name}, region: {region}")
        logger.info(f"=" * 60)
        
        # Scrape team data
        team_data = team_scraper.get_team_events_data(team_name, region=region)
        
        if 'error' in team_data:
            logger.error(f"Error in team_data: {team_data['error']}")
            return jsonify(team_data), 404
        
        # Log the raw data before processing
        for event in team_data.get('events', []):
            logger.info(f"Event: {event.get('event_name')} - Matches: {event.get('matches_played')}, Rounds: {event.get('total_rounds')}")
        
        # Process team data
        processor = TeamProcessor()
        analysis = processor.process_team_data(team_data)
        
        # Log the processed data
        for event in analysis.get('events', []):
            logger.info(f"PROCESSED Event: {event.get('event_name')} - Matches: {event.get('matches_played')}, Rounds: {event.get('total_rounds')}")
        
        logger.info(f"=" * 60)
        
        response = jsonify({
            'success': True,
            'analysis': analysis
        })
        # Prevent browser caching to ensure fresh data
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
        return response
        
    except Exception as e:
        logger.error(f"Error processing team {team_name}: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/api/prizepicks/<ign>', methods=['GET'])
def get_prizepicks_analysis(ign):
    """Get PrizePicks analysis for a specific player.
    Query: line, combo_maps (2=Bo3 Maps 1+2, 3=Bo5 Maps 1+2+3)
    """
    try:
        kill_line = float(request.args.get('line', 30.5))
        combo_maps = int(request.args.get('combo_maps', 2))
        combo_maps = 2 if combo_maps not in (2, 3) else combo_maps
        
        processor = PrizePicksProcessor(kill_line=kill_line, combo_maps=combo_maps)
        
        logger.info(f"Scraping PrizePicks data for player: {ign} with kill line: {kill_line}")
        
        # Scrape match-level data from VLR.gg
        player_data = pp_scraper.get_player_prizepicks_data(ign, kill_line=kill_line)
        
        if not player_data or not player_data.get('ign'):
            return jsonify({'error': 'Player not found'}), 404
        
        # Perform analysis
        analysis = processor.evaluate_prizepicks_line(player_data)

        matchup = _parse_matchup_inputs(request.args)
        if matchup.get('invalid_error'):
            return jsonify({'error': matchup['invalid_error']}), 400
        if matchup.get('provided'):
            combo_samples = []
            for match_data in player_data.get('match_combinations', []):
                map_kills = [k for k in match_data.get('map_kills', []) if k is not None and k > 0]
                if len(map_kills) < 2:
                    continue
                combos = processor.process_match_combinations(map_kills)
                combo_samples.extend([c['combined_kills'] for c in combos])

            if len(combo_samples) >= 3:
                dist_params = compute_distribution_params(combo_samples)
                adj = apply_matchup_adjustment(dist_params, matchup['team_win_prob'])
                adjusted_probs = compute_prop_probabilities(adj['dist_params'], kill_line)
                analysis['matchup_adjusted_probabilities'] = {
                    'p_over': adjusted_probs['p_over'],
                    'p_under': adjusted_probs['p_under'],
                    'team_win_prob': matchup['team_win_prob'],
                    'mu_base': adj.get('mu_base'),
                    'mu_adjusted': adj.get('mu_adjusted'),
                    'multiplier': adj.get('multiplier'),
                    'components': adj.get('components', {}),
                    'input_method': matchup.get('method')
                }
        
        # Return response
        return jsonify({
            'success': True,
            'analysis': analysis,
            'player_info': {
                'ign': player_data['ign'],
                'team': player_data.get('team', 'Unknown'),
                'matches_count': len(player_data.get('match_combinations', []))
            }
        })
        
    except Exception as e:
        logger.error(f"Error processing PrizePicks for {ign}: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/api/prizepicks/edge/<ign>', methods=['GET'])
def get_prizepicks_edge_analysis(ign):
    """
    Get mathematical edge analysis for PrizePicks combined props.
    Query: line, combo_maps (2 or 3), over_odds, under_odds
    """
    try:
        line = float(request.args.get('line', 30.5))
        combo_maps = int(request.args.get('combo_maps', 2))
        combo_maps = 2 if combo_maps not in (2, 3) else combo_maps
        over_odds = float(request.args.get('over_odds', -110))
        under_odds = float(request.args.get('under_odds', -110))
        matchup = _parse_matchup_inputs(request.args)
        if matchup.get('invalid_error'):
            return jsonify({'error': matchup['invalid_error']}), 400

        logger.info(f"PrizePicks edge analysis for {ign}: line={line}, combo_maps={combo_maps}")

        player_data = pp_scraper.get_player_prizepicks_data(ign, kill_line=line)
        if not player_data or not player_data.get('ign'):
            return jsonify({'error': 'Player not found'}), 404

        pp_processor = PrizePicksProcessor(kill_line=line, combo_maps=combo_maps)
        combo_samples = []

        for match_data in player_data.get('match_combinations', []):
            map_kills = [k for k in match_data.get('map_kills', []) if k is not None and k > 0]
            if len(map_kills) < 2:
                continue
            combos = pp_processor.process_match_combinations(map_kills)
            combo_samples.extend([c['combined_kills'] for c in combos])

        if len(combo_samples) < 3:
            return jsonify({'error': f'Insufficient {combo_maps}-map combination samples for edge analysis'}), 400

        # Model distribution from combined 2-map kills
        dist_params = compute_distribution_params(combo_samples)
        dist_params['samples'] = combo_samples

        # Probabilities from model
        adj = apply_matchup_adjustment(dist_params, matchup.get('team_win_prob'))
        dist_for_probs = adj['dist_params']
        model_probs = compute_prop_probabilities(dist_for_probs, line)

        # Market implied probabilities/mean
        market_params = compute_market_parameters(
            line=line,
            over_odds=over_odds,
            under_odds=under_odds,
            model_dist_type=dist_for_probs['dist'],
            model_dispersion=dist_for_probs.get('k', None)
        )

        p_over_model = model_probs['p_over']
        p_under_model = model_probs['p_under']
        p_over_market = market_params['p_over_vigfree']
        p_under_market = market_params['p_under_vigfree']

        prob_edge_over = p_over_model - p_over_market
        prob_edge_under = p_under_model - p_under_market

        ev_over = expected_value_per_1(p_over_model, over_odds)
        ev_under = expected_value_per_1(p_under_model, under_odds)

        if ev_over > 0 and ev_over > ev_under:
            recommended = 'OVER'
            best_ev = ev_over
        elif ev_under > 0 and ev_under > ev_over:
            recommended = 'UNDER'
            best_ev = ev_under
        else:
            recommended = 'NO BET'
            best_ev = max(ev_over, ev_under)

        # Visualization PMFs around combined-kill mean
        mu = dist_for_probs['mu']
        x_min = max(0, int(mu - 25))
        x_max = int(mu + 25)
        model_pmf = generate_pmf(dist_for_probs, (x_min, x_max))

        market_dist_params = {
            'dist': dist_for_probs['dist'],
            'mu': market_params['mu_market'],
            'lambda': market_params['mu_market'],
        }
        if dist_for_probs['dist'] == 'nbinom':
            k = dist_for_probs.get('k', 1.0)
            market_dist_params['k'] = k
            market_dist_params['p'] = k / (k + market_params['mu_market'])
        market_pmf = generate_pmf(market_dist_params, (x_min, x_max))

        return jsonify({
            'success': True,
            'scope': f'prizepicks_{combo_maps}map_combo',
            'player': {
                'ign': ign,
                'sample_size': len(combo_samples),
                'confidence': dist_params['confidence']
            },
            'line': line,
            'model': {
                'dist': dist_for_probs['dist'],
                'mu': dist_for_probs['mu'],
                'var': dist_for_probs['var'],
                'p_over': p_over_model,
                'p_under': p_under_model
            },
            'matchup_adjustment': {
                'applied': adj.get('applied', False),
                'team_win_prob': matchup.get('team_win_prob'),
                'input_method': matchup.get('method'),
                'mu_base': adj.get('mu_base'),
                'mu_adjusted': adj.get('mu_adjusted'),
                'multiplier': adj.get('multiplier'),
                'components': adj.get('components', {})
            },
            'market': {
                'over_odds': over_odds,
                'under_odds': under_odds,
                'p_over_vigfree': p_over_market,
                'p_under_vigfree': p_under_market,
                'vig_percentage': market_params['vig_percentage'],
                'mu_implied': market_params['mu_market']
            },
            'edge': {
                'prob_edge_over': prob_edge_over,
                'prob_edge_under': prob_edge_under,
                'ev_over': ev_over,
                'ev_under': ev_under,
                'recommended': recommended,
                'best_ev': best_ev,
                'roi_over_pct': ev_over * 100,
                'roi_under_pct': ev_under * 100
            },
            'visualization': {
                'x': model_pmf['x'],
                'model_pmf': model_pmf['pmf'],
                'market_pmf': market_pmf['pmf'],
                'line_position': line
            }
        })

    except Exception as e:
        logger.error(f"Error in PrizePicks edge analysis for {ign}: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/api/prizepicks/parlay', methods=['POST'])
def get_prizepicks_parlay_analysis():
    """
    Simulate PrizePicks parlay hit rate and EV.
    Payload: legs: [...], combo_maps: 2 or 3 (optional, default 2)
    """
    try:
        payload = request.get_json(silent=True) or {}
        legs = payload.get('legs', [])
        combo_maps = int(payload.get('combo_maps', 2))
        combo_maps = 2 if combo_maps not in (2, 3) else combo_maps

        if not isinstance(legs, list) or len(legs) < 2 or len(legs) > 6:
            return jsonify({'error': 'Parlay must contain 2 to 6 legs'}), 400

        payout_map = {2: 3.0, 3: 6.0, 4: 10.0, 5: 20.0, 6: 37.5}
        payout_multiplier = payout_map[len(legs)]

        use_challengers = payload.get('challengers', False)
        get_data_fn = pp_scraper.get_player_prizepicks_data_challengers if use_challengers else pp_scraper.get_player_prizepicks_data

        leg_results = []
        parlay_hit_prob = 1.0

        for i, leg in enumerate(legs):
            ign = str(leg.get('ign', '')).strip()
            side = str(leg.get('side', '')).strip().lower()
            line = float(leg.get('line', 0))

            if not ign:
                return jsonify({'error': f'Leg {i+1}: missing player name'}), 400
            if side not in ('over', 'under'):
                return jsonify({'error': f'Leg {i+1}: side must be "over" or "under"'}), 400
            if line <= 0:
                return jsonify({'error': f'Leg {i+1}: line must be positive'}), 400

            player_data = get_data_fn(ign, kill_line=line)
            if not player_data or not player_data.get('ign'):
                return jsonify({'error': f'Leg {i+1}: player not found ({ign})'}), 404

            pp_processor = PrizePicksProcessor(kill_line=line, combo_maps=combo_maps)
            combo_samples = []
            for match_data in player_data.get('match_combinations', []):
                map_kills = [k for k in match_data.get('map_kills', []) if k is not None and k > 0]
                if len(map_kills) < 2:
                    continue
                combos = pp_processor.process_match_combinations(map_kills)
                combo_samples.extend([c['combined_kills'] for c in combos])

            if len(combo_samples) < 3:
                return jsonify({'error': f'Leg {i+1}: insufficient sample size for {ign}'}), 400

            dist_params = compute_distribution_params(combo_samples)
            probs = compute_prop_probabilities(dist_params, line)

            p_over = probs['p_over']
            p_under = probs['p_under']
            leg_hit_prob = p_over if side == 'over' else p_under
            parlay_hit_prob *= leg_hit_prob

            leg_results.append({
                'ign': player_data.get('ign', ign),
                'team': player_data.get('team', 'Unknown'),
                'line': line,
                'side': side,
                'p_hit': leg_hit_prob,
                'p_over': p_over,
                'p_under': p_under,
                'sample_size': len(combo_samples),
                'mu': dist_params.get('mu', 0.0),
                'var': dist_params.get('var', 0.0),
                'dist': dist_params.get('dist', 'poisson')
            })

        expected_return_per_1 = parlay_hit_prob * payout_multiplier
        ev_per_1 = expected_return_per_1 - 1.0
        roi_pct = ev_per_1 * 100

        return jsonify({
            'success': True,
            'legs_count': len(legs),
            'payout_multiplier': payout_multiplier,
            'parlay_hit_probability': parlay_hit_prob,
            'expected_return_per_1': expected_return_per_1,
            'ev_per_1': ev_per_1,
            'roi_pct': roi_pct,
            'legs': leg_results,
            'assumption': 'Leg outcomes are treated as independent for parlay probability.'
        })

    except Exception as e:
        logger.error(f"Error in PrizePicks parlay analysis: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


def _build_leaderboard_from_projections(projections: list, combo_maps: int = 2, use_challengers: bool = False) -> tuple:
    """Shared logic: take list of {player_name, line}, fetch VLR data (or use cache), compute ranks.
    combo_maps: 2 for Bo3 (Maps 1+2), 3 for Bo5 (Maps 1+2+3)
    use_challengers: if True, use Challengers (tier 2) stats only

    Speed strategy:
      Phase 1 – normalize names + check DB/session cache for every player (fast, serial, no network).
      Phase 2 – fetch uncached players in parallel using ThreadPoolExecutor (4 workers).
      Phase 3 – compute combo samples + distribution stats for all players (fast, serial, in-memory).
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    get_data   = pp_scraper.get_player_prizepicks_data_challengers if use_challengers else pp_scraper.get_player_prizepicks_data
    get_cache  = db.get_cached_player_data_challengers if use_challengers else db.get_cached_player_data
    save_cache = db.save_player_data_cache_challengers if use_challengers else db.save_player_data_cache
    get_combo  = db.get_cached_combo_samples_challengers if use_challengers else db.get_cached_combo_samples
    save_combo = db.save_combo_cache_challengers if use_challengers else db.save_combo_cache

    # ── Phase 1: normalize names + check all DB/session caches (no network I/O) ──
    normalized: list = []   # ordered (pp_name, line) — same order as projections
    player_cache: dict = {} # pp_name → player_data | None
    name_to_line: dict = {} # first kill_line seen per name (for live fetch call)

    for proj in projections:
        pp_name = proj.get('player_name', '').strip()
        if pp_name and not pp_name.startswith('Unknown_'):
            pp_name = re.sub(r'\.{2,}$|…+$', '', pp_name).strip('.\t ')
        line = proj.get('line')
        if not pp_name or line is None:
            continue
        normalized.append((pp_name, line))
        if pp_name not in player_cache:
            player_cache[pp_name] = get_cache(pp_name)  # None if not cached
        if pp_name not in name_to_line:
            name_to_line[pp_name] = line

    # ── Phase 2: parallel-fetch players not in DB/session cache ──
    seen_unc: set = set()
    unique_uncached: list = []
    for pp_name, _ in normalized:
        if player_cache.get(pp_name) is None and pp_name not in seen_unc:
            seen_unc.add(pp_name)
            unique_uncached.append(pp_name)

    if unique_uncached:
        print(f"[UPLOAD] {len(unique_uncached)} players not cached — fetching in parallel (4 workers)...", flush=True)

        def _fetch_player(name: str):
            try:
                data = get_data(name, kill_line=name_to_line[name])
                if data:
                    save_cache(name, data)
                return name, data
            except Exception as exc:
                logger.warning(f"[UPLOAD] fetch error for {name}: {exc}")
                return name, None

        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = {executor.submit(_fetch_player, name): name for name in unique_uncached}
            done = 0
            for future in as_completed(futures):
                name, data = future.result()
                player_cache[name] = data
                done += 1
                print(f"[UPLOAD] Fetched {done}/{len(unique_uncached)}: {name} ({'ok' if data else 'not found'})", flush=True)
    else:
        print(f"[UPLOAD] All {len(normalized)} players found in cache — skipping network fetch.", flush=True)

    # ── Phase 3: compute combo samples + distribution stats (in-memory, serial) ──
    results: list = []
    skipped: list = []
    n_total = len(normalized)

    for idx, (pp_name, line) in enumerate(normalized):
        if (idx + 1) % 10 == 0 or idx == 0:
            print(f"[UPLOAD] Stats {idx + 1}/{n_total}: {pp_name}", flush=True)

        player_data = player_cache.get(pp_name)
        if not player_data or not player_data.get('ign'):
            skipped.append({'player_name': pp_name, 'line': line, 'reason': 'Player not found on VLR'})
            continue

        pp_processor = PrizePicksProcessor(kill_line=line, combo_maps=combo_maps)
        combo_samples = get_combo(pp_name, combo_maps=combo_maps)
        if combo_samples is None:
            combo_samples = []
            for match_data in player_data.get('match_combinations', []):
                map_kills = [k for k in match_data.get('map_kills', []) if k is not None and k > 0]
                if len(map_kills) < 2:
                    continue
                combos = pp_processor.process_match_combinations(map_kills)
                combo_samples.extend([c['combined_kills'] for c in combos])
            if combo_samples:
                save_combo(pp_name, combo_samples, combo_maps=combo_maps)

        if len(combo_samples) < 3:
            skipped.append({'player_name': pp_name, 'line': line, 'reason': f'Insufficient data ({len(combo_samples)} combo samples)'})
            continue

        dist_params = compute_distribution_params(combo_samples)
        probs = compute_prop_probabilities(dist_params, line)
        p_over, p_under = probs['p_over'], probs['p_under']
        best_side = 'over' if p_over >= p_under else 'under'
        p_hit = p_over if best_side == 'over' else p_under
        results.append({
            'rank': 0,
            'player_name': pp_name,
            'vlr_ign': player_data.get('ign', pp_name),
            'team': player_data.get('team', 'Unknown'),
            'line': line,
            'best_side': best_side,
            'p_hit': round(p_hit, 4),
            'p_over': round(p_over, 4),
            'p_under': round(p_under, 4),
            'sample_size': len(combo_samples),
            'mu': round(dist_params.get('mu', 0), 2),
            'dist_type': dist_params.get('dist', 'poisson'),
            'dist_var': round(float(dist_params.get('var', dist_params.get('mu', 1))), 4),
            'dist_k': round(float(dist_params['k']), 4) if dist_params.get('dist') == 'nbinom' and 'k' in dist_params else None,
        })

    results.sort(key=lambda x: x['p_hit'], reverse=True)
    for i, r in enumerate(results, 1):
        r['rank'] = i
    print(f"[UPLOAD] Done: {len(results)} ranked, {len(skipped)} skipped", flush=True)
    return results, skipped


@app.route('/api/prizepicks/leaderboard', methods=['GET'])
def get_prizepicks_leaderboard():
    """
    Fetch Valorant lines from PrizePicks API and rank by hit probability (best to worst).
    Each line is evaluated with our model; best side (Over/Under) is chosen.
    """
    try:
        try:
            projections = fetch_valorant_projections(stat_filter=['kill'])
        except Exception as fetch_err:
            status = getattr(getattr(fetch_err, 'response', None), 'status_code', None)
            if status == 403:
                return jsonify({
                    'success': True,
                    'leaderboard': [],
                    'message': 'PrizePicks API is blocking automated access (403 – Cloudflare protection). Try using a VPN or different network; or enter lines manually in the search below.'
                })
            raise
        if not projections:
            return jsonify({
                'success': True,
                'leaderboard': [],
                'message': 'No Valorant kill lines available from PrizePicks (may be off-season or API unavailable).'
            })

        results, skipped = _build_leaderboard_from_projections(projections)
        if results:
            db.save_leaderboard_snapshot('api', results, parsed_count=len(projections))
        return jsonify({
            'success': True,
            'leaderboard': results,
            'skipped': skipped,
            'fetched_at': projections[0].get('description', '') if projections else '',
        })

    except Exception as e:
        logger.error(f"Error building PrizePicks leaderboard: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@app.route('/api/challengers/prizepicks/leaderboard', methods=['GET'])
def get_challengers_prizepicks_leaderboard():
    """Fetch PrizePicks Valorant lines and rank by Challengers hit probability"""
    try:
        try:
            projections = fetch_valorant_projections(stat_filter=['kill'])
        except Exception as fetch_err:
            status = getattr(getattr(fetch_err, 'response', None), 'status_code', None)
            if status == 403:
                return jsonify({
                    'success': True, 'leaderboard': [],
                    'message': 'PrizePicks API blocking. Try VPN or enter lines manually.'
                })
            raise
        if not projections:
            return jsonify({
                'success': True, 'leaderboard': [],
                'message': 'No Valorant kill lines from PrizePicks.'
            })
        results, skipped = _build_leaderboard_from_projections(projections, use_challengers=True)
        if results:
            db.save_leaderboard_snapshot('challengers_api', results, parsed_count=len(projections))
        return jsonify({
            'success': True,
            'leaderboard': results,
            'skipped': skipped,
            'fetched_at': projections[0].get('description', '') if projections else '',
        })
    except Exception as e:
        logger.error(f"Error building Challengers leaderboard: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@app.route('/api/prizepicks/leaderboard/upload', methods=['POST'])
def upload_leaderboard_image():
    """
    Upload PrizePicks screenshot(s); Gemini vision parses player names and lines, then ranks by hit probability.
    
    Query params (optional):
        combo_maps: 2 (Bo3) or 3 (Bo5) to override auto-detection
    
    Requires GOOGLE_API_KEY or GEMINI_API_KEY (free at https://aistudio.google.com/apikey)
    
    Supports single or multiple file upload:
        - Single: 'image' or 'file' field
        - Multiple: 'images' or 'files' field (array)
    """
    try:
        print("[UPLOAD] Screenshot upload received", flush=True)
        try:
            from scraper.vision_parser import parse_prizepicks_image_vision, parse_prizepicks_images_batch_vision
        except ImportError as ie:
            return jsonify({
                'error': f'Vision parser not available: {ie}. Install: pip install google-generativeai. Set GOOGLE_API_KEY (free at https://aistudio.google.com/apikey)'
            }), 500

        # Manual override: combo_maps=2 (Bo3) or combo_maps=3 (Bo5)
        combo_maps_override = request.args.get('combo_maps', '').strip()
        if combo_maps_override in ('2', '3'):
            combo_maps_override = int(combo_maps_override)
        else:
            combo_maps_override = None
        use_challengers = request.args.get('challengers', 'false').lower() == 'true'
        
        # Check for multiple files
        files = request.files.getlist('images') or request.files.getlist('files')
        
        if not files:
            # Single file mode
            if 'image' not in request.files and 'file' not in request.files:
                return jsonify({'error': 'No image file provided'}), 400
            f = request.files.get('image') or request.files.get('file')
            if not f or f.filename == '':
                return jsonify({'error': 'No image file selected'}), 400
            files = [f]
        
        # Read all images
        image_bytes_list = []
        for f in files:
            img_bytes = f.read()
            if len(img_bytes) < 100:
                logger.warning(f"Skipping {f.filename}: file too small")
                continue
            image_bytes_list.append(img_bytes)
        
        if not image_bytes_list:
            return jsonify({'error': 'No valid image files provided'}), 400
        
        # Parse images with Gemini vision
        print(f"[UPLOAD] Running vision on {len(image_bytes_list)} image(s)...", flush=True)
        if len(image_bytes_list) == 1:
            projections, combo_maps = parse_prizepicks_image_vision(image_bytes_list[0])
        else:
            projections, combo_maps = parse_prizepicks_images_batch_vision(image_bytes_list)
        if combo_maps_override is not None:
            combo_maps = combo_maps_override
            print(f"[UPLOAD] Vision done: {len(projections)} lines; using manual combo_maps={combo_maps}", flush=True)
        else:
            print(f"[UPLOAD] Vision done: {len(projections)} lines, combo_maps={combo_maps} (auto-detected)", flush=True)
        
        if not projections:
            return jsonify({
                'success': True,
                'leaderboard': [],
                'images_processed': len(image_bytes_list),
                'message': 'Could not parse any lines from the image(s). Ensure they show PrizePicks Valorant kill cards (MAPS 1-2 or MAPS 1-3 Kills).'
            })

        print(f"[UPLOAD] Building leaderboard for {len(projections)} players (VLR lookups - may take a minute)...", flush=True)
        results, skipped = _build_leaderboard_from_projections(projections, combo_maps=combo_maps, use_challengers=use_challengers)
        print(f"[UPLOAD] Done: {len(results)} ranked, {len(skipped)} skipped", flush=True)
        if results:
            base = 'challengers_' if use_challengers else ''
            source = base + ('batch_upload' if len(image_bytes_list) > 1 else 'upload')
            db.save_leaderboard_snapshot(source, results, parsed_count=len(projections))
        
        # Include skipped entries in leaderboard with N/A values so user can see all detected lines
        skipped_entries = [
            {
                'rank': 0,
                'player_name': s['player_name'],
                'vlr_ign': s['player_name'],
                'team': 'N/A',
                'line': s['line'],
                'best_side': 'N/A',
                'p_hit': None,
                'p_over': None,
                'p_under': None,
                'sample_size': None,
                'mu': None,
                'incomplete': True,
                'reason': s['reason'],
            }
            for s in skipped
        ]
        combined_leaderboard = results + skipped_entries
        
        skip_msg = ''
        if skipped:
            skip_msg = f' {len(skipped)} without data (shown as N/A): ' + '; '.join(s[:50] for s in [f"{s['player_name']} ({s['reason']})" for s in skipped[:5]])
            if len(skipped) > 5:
                skip_msg += f' ...'
        
        batch_info = f' from {len(image_bytes_list)} image(s)' if len(image_bytes_list) > 1 else ''
        combo_label = 'Maps 1+2+3 (Bo5)' if combo_maps == 3 else 'Maps 1+2 (Bo3)'
        
        return jsonify({
            'success': True,
            'leaderboard': combined_leaderboard,
            'skipped': skipped,
            'combo_maps': combo_maps,
            'images_processed': len(image_bytes_list),
            'parsed_count': len(projections),
            'message': f'Parsed {len(projections)} lines ({combo_label}){batch_info}; ranked {len(results)} with sufficient data. All {len(combined_leaderboard)} shown.' + (f' {skip_msg}' if skip_msg else '')
        })
    except Exception as e:
        logger.error(f"Error processing leaderboard image: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@app.route('/api/prizepicks/leaderboard/apply-matchup', methods=['POST'])
def apply_leaderboard_matchup():
    """
    Parse a betting odds screenshot and apply matchup adjustments to leaderboard rows.

    Form data:
        image / file: odds screenshot (required)
        leaderboard:  JSON string of current leaderboard rows (required)

    Returns adjusted leaderboard with adj_p_over, adj_p_under, adj_p_hit, matchup_info added.
    """
    try:
        try:
            from scraper.vision_parser import parse_matchup_odds_image_vision
        except ImportError as ie:
            return jsonify({'error': f'Vision parser not available: {ie}. Install: pip install google-generativeai'}), 500

        f = request.files.get('image') or request.files.get('file')
        if not f or f.filename == '':
            logger.warning("[MATCHUP] 400: no image file in request")
            return jsonify({'error': 'No odds image provided'}), 400
        img_bytes = f.read()
        if len(img_bytes) < 100:
            logger.warning(f"[MATCHUP] 400: image too small ({len(img_bytes)} bytes)")
            return jsonify({'error': 'Image file too small or empty'}), 400

        lb_json = request.form.get('leaderboard', '[]')
        logger.info(f"[MATCHUP] leaderboard field length: {len(lb_json)} chars")
        try:
            leaderboard = json.loads(lb_json)
        except (ValueError, Exception) as json_err:
            logger.warning(f"[MATCHUP] 400: json.loads failed — {json_err!r} — first 200 chars: {lb_json[:200]!r}")
            return jsonify({'error': 'Invalid leaderboard JSON'}), 400
        if not leaderboard:
            logger.warning("[MATCHUP] 400: leaderboard is empty after parse")
            return jsonify({'error': 'No leaderboard data provided. Load a leaderboard first.'}), 400

        print("[MATCHUP] Parsing odds screenshot with Gemini...", flush=True)
        matchups = parse_matchup_odds_image_vision(img_bytes)
        if not matchups:
            logger.warning("[MATCHUP] 400: Gemini returned no matchups from image")
            return jsonify({
                'success': False,
                'error': 'Could not parse any team odds from the image. Make sure the screenshot shows moneyline odds (e.g. Sentinels -150 vs NRG +130).'
            }), 400
        print(f"[MATCHUP] Parsed {len(matchups)} matchup(s): {matchups}", flush=True)

        def _normalize(name):
            import re as _re
            return _re.sub(r'[^a-z0-9 ]', '', name.lower()).strip()

        # Build lookup: normalized_team -> (team_odds, opp_odds)
        team_odds_lookup = {}
        for m in matchups:
            t1 = _normalize(m['team1'])
            t2 = _normalize(m['team2'])
            o1 = m['team1_odds']
            o2 = m['team2_odds']
            team_odds_lookup[t1] = (o1, o2)
            team_odds_lookup[t2] = (o2, o1)

        def _find_team_odds(team_name):
            if not team_name or team_name in ('N/A', 'Unknown', ''):
                return None, None
            norm = _normalize(team_name)
            if norm in team_odds_lookup:
                return team_odds_lookup[norm]
            # Substring match
            for key, odds in team_odds_lookup.items():
                if norm in key or key in norm:
                    return odds
            # First-word match
            first = norm.split()[0] if norm.split() else ''
            if first:
                for key, odds in team_odds_lookup.items():
                    if key.startswith(first) or first in key:
                        return odds
            return None, None

        adjusted_leaderboard = []
        matched_count = 0
        unmatched_teams = set()

        for row in leaderboard:
            new_row = dict(row)
            if row.get('incomplete') or row.get('p_over') is None:
                adjusted_leaderboard.append(new_row)
                continue

            team = row.get('team', '')
            t_odds, o_odds = _find_team_odds(team)
            if t_odds is None:
                unmatched_teams.add(team)
                adjusted_leaderboard.append(new_row)
                continue

            try:
                matchup_info = infer_team_win_probability(team_odds=t_odds, opp_odds=o_odds)
            except ValueError:
                unmatched_teams.add(team)
                adjusted_leaderboard.append(new_row)
                continue

            if not matchup_info.get('provided'):
                adjusted_leaderboard.append(new_row)
                continue

            mu = float(row.get('mu') or 1.0)
            dist_type = row.get('dist_type', 'poisson')
            dist_var = float(row.get('dist_var') or mu)
            dist_k = row.get('dist_k')

            dist_params_approx = {'mu': mu, 'var': dist_var, 'dist': dist_type}
            if dist_type == 'poisson':
                dist_params_approx['lambda'] = mu
            elif dist_type == 'nbinom' and dist_k is not None:
                k = float(dist_k)
                dist_params_approx['k'] = k
                dist_params_approx['p'] = k / (k + mu)

            team_win_prob = matchup_info['team_win_prob']
            adj_result = apply_matchup_adjustment(dist_params_approx, team_win_prob)
            adj_params = adj_result['dist_params']

            line = float(row.get('line', 0))
            adj_probs = compute_prop_probabilities(adj_params, line)
            adj_p_over = adj_probs['p_over']
            adj_p_under = adj_probs['p_under']
            adj_best_side = 'over' if adj_p_over >= adj_p_under else 'under'
            adj_p_hit = adj_p_over if adj_best_side == 'over' else adj_p_under

            new_row['adj_p_over'] = round(adj_p_over, 4)
            new_row['adj_p_under'] = round(adj_p_under, 4)
            new_row['adj_p_hit'] = round(adj_p_hit, 4)
            new_row['adj_best_side'] = adj_best_side
            new_row['matchup_info'] = {
                'team_win_prob': round(team_win_prob, 4),
                'team_odds': t_odds,
                'opp_odds': o_odds,
                'multiplier': round(adj_result.get('multiplier', 1.0), 4),
                'mu_base': round(adj_result.get('mu_base', mu), 3),
                'mu_adjusted': round(adj_result.get('mu_adjusted', mu), 3),
            }
            matched_count += 1
            adjusted_leaderboard.append(new_row)

        # Re-sort ranked rows by adj_p_hit (or p_hit if no adjustment)
        ranked = [r for r in adjusted_leaderboard if not r.get('incomplete')]
        unranked = [r for r in adjusted_leaderboard if r.get('incomplete')]
        ranked.sort(key=lambda r: r.get('adj_p_hit') or r.get('p_hit') or 0, reverse=True)
        for i, r in enumerate(ranked, 1):
            r['rank'] = i
        adjusted_leaderboard = ranked + unranked

        eligible = len([r for r in leaderboard if not r.get('incomplete') and r.get('p_over') is not None])
        return jsonify({
            'success': True,
            'leaderboard': adjusted_leaderboard,
            'matchups_parsed': matchups,
            'matched_count': matched_count,
            'unmatched_teams': list(unmatched_teams),
            'message': f'Applied matchup odds to {matched_count} of {eligible} players from {len(matchups)} matchup(s).'
        })

    except ImportError as e:
        return jsonify({'error': str(e)}), 500
    except Exception as e:
        logger.error(f"Error applying leaderboard matchup: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@app.route('/api/prizepicks/leaderboard/history', methods=['GET'])
def get_leaderboard_history():
    """List recent leaderboard snapshots. ?challengers=true filters to Challengers snapshots."""
    try:
        limit = int(request.args.get('limit', 50))
        limit = min(limit, 200)
        snapshots = db.get_leaderboard_snapshots(limit=limit)
        if request.args.get('challengers', 'false').lower() == 'true':
            snapshots = [s for s in snapshots if s.get('source', '').startswith('challengers')]
        return jsonify({'success': True, 'snapshots': snapshots})
    except Exception as e:
        logger.error(f"Error getting leaderboard history: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@app.route('/api/prizepicks/leaderboard/<int:snapshot_id>', methods=['GET'])
def get_leaderboard_history_item(snapshot_id):
    """Get a specific leaderboard snapshot by ID."""
    try:
        snapshot = db.get_leaderboard_snapshot(snapshot_id)
        if not snapshot:
            return jsonify({'error': 'Snapshot not found'}), 404
        return jsonify({'success': True, **snapshot})
    except Exception as e:
        logger.error(f"Error getting leaderboard snapshot: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


# Add error handler for 404 to debug (at end of file, after all routes)
@app.errorhandler(404)
def handle_404(e):
    logger.error(f"404 Not Found: {request.path}")
    return jsonify({'error': 'Not Found', 'path': request.path}), 404

if __name__ == '__main__':
    app.run(debug=True, port=5000)
