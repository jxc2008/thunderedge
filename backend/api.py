# backend/api.py
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scraper.vlr_scraper import VLRScraper
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
from config import Config
import logging

app = Flask(__name__, static_folder='../frontend', template_folder='../frontend/templates')
CORS(app)

# Initialize logging first
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize components
db = Database(Config.DATABASE_PATH)
scraper = VLRScraper(database=db)  # Inject database for caching
team_scraper = TeamScraper(database=db)

# Add request logging middleware (after logger is initialized)
@app.before_request
def log_request_info():
    logger.info(f"REQUEST: {request.method} {request.path}")
    if request.args:
        logger.info(f"Query params: {request.args}")

@app.after_request
def log_response_info(response):
    logger.info(f"RESPONSE: {response.status_code} for {request.path}")
    return response

# Add error handler for 404 to debug (must be after routes are defined)


@app.route('/')
def index():
    """Serve the frontend"""
    return send_from_directory('../frontend/templates', 'index.html')

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
        
        logger.info(f"Edge analysis for {ign}: line={line}, over={over_odds}, under={under_odds}")
        
        # Step 1: Get player's distribution from cached data
        context = {'last_n': last_n} if last_n else {}
        dist_params = get_player_distribution(db, ign, context=context)
        
        if 'error' in dist_params:
            return jsonify({'error': dist_params['error']}), 404
        
        # Step 2: Compute model probabilities
        model_probs = compute_prop_probabilities(dist_params, line)
        
        # Step 3: Compute market-implied parameters
        market_params = compute_market_parameters(
            line=line,
            over_odds=over_odds,
            under_odds=under_odds,
            model_dist_type=dist_params['dist'],
            model_dispersion=dist_params.get('k', None)
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
        mu = dist_params['mu']
        x_min = max(0, int(mu - 15))
        x_max = int(mu + 15)
        model_pmf = generate_pmf(dist_params, (x_min, x_max))
        
        # Generate market PMF (using market-implied params)
        market_dist_params = {
            'dist': dist_params['dist'],
            'mu': market_params['mu_market'],
            'lambda': market_params['mu_market'],  # for Poisson
        }
        if dist_params['dist'] == 'nbinom':
            # Use same dispersion as model for market PMF
            market_dist_params['k'] = dist_params.get('k', 1.0)
            k = dist_params.get('k', 1.0)
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
                'dist': dist_params['dist'],
                'mu': dist_params['mu'],
                'var': dist_params['var'],
                'p_over': p_over_model,
                'p_under': p_under_model,
                'samples': dist_params.get('samples', [])[:20]  # First 20 for debugging
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
        player_data = scraper.get_player_prizepicks_data(ign, kill_line=kill_line)
        
        if not player_data or not player_data.get('ign'):
            return jsonify({'error': 'Player not found'}), 404
        
        # Perform analysis
        analysis = processor.evaluate_prizepicks_line(player_data)
        
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

        logger.info(f"PrizePicks edge analysis for {ign}: line={line}, combo_maps={combo_maps}")

        player_data = scraper.get_player_prizepicks_data(ign, kill_line=line)
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
        model_probs = compute_prop_probabilities(dist_params, line)

        # Market implied probabilities/mean
        market_params = compute_market_parameters(
            line=line,
            over_odds=over_odds,
            under_odds=under_odds,
            model_dist_type=dist_params['dist'],
            model_dispersion=dist_params.get('k', None)
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
        mu = dist_params['mu']
        x_min = max(0, int(mu - 25))
        x_max = int(mu + 25)
        model_pmf = generate_pmf(dist_params, (x_min, x_max))

        market_dist_params = {
            'dist': dist_params['dist'],
            'mu': market_params['mu_market'],
            'lambda': market_params['mu_market'],
        }
        if dist_params['dist'] == 'nbinom':
            k = dist_params.get('k', 1.0)
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
                'dist': dist_params['dist'],
                'mu': dist_params['mu'],
                'var': dist_params['var'],
                'p_over': p_over_model,
                'p_under': p_under_model
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

            player_data = scraper.get_player_prizepicks_data(ign, kill_line=line)
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


def _build_leaderboard_from_projections(projections: list, combo_maps: int = 2) -> tuple:
    """Shared logic: take list of {player_name, line}, fetch VLR data (or use cache), compute ranks.
    combo_maps: 2 for Bo3 (Maps 1+2), 3 for Bo5 (Maps 1+2+3)"""
    player_cache = {}
    results = []
    skipped = []
    for proj in projections:
        pp_name = proj.get('player_name', '').strip()
        line = proj.get('line')
        if not pp_name or line is None:
            continue
        if pp_name not in player_cache:
            player_data = db.get_cached_player_data(pp_name)
            if not player_data:
                player_data = scraper.get_player_prizepicks_data(pp_name, kill_line=line)
                if player_data:
                    db.save_player_data_cache(pp_name, player_data)
            player_cache[pp_name] = player_data
        else:
            player_data = player_cache[pp_name]
        if not player_data or not player_data.get('ign'):
            skipped.append({'player_name': pp_name, 'line': line, 'reason': 'Player not found on VLR'})
            continue
        pp_processor = PrizePicksProcessor(kill_line=line, combo_maps=combo_maps)
        combo_samples = db.get_cached_combo_samples(pp_name, combo_maps=combo_maps)
        if combo_samples is None:
            combo_samples = []
            for match_data in player_data.get('match_combinations', []):
                map_kills = [k for k in match_data.get('map_kills', []) if k is not None and k > 0]
                if len(map_kills) < 2:
                    continue
                combos = pp_processor.process_match_combinations(map_kills)
                combo_samples.extend([c['combined_kills'] for c in combos])
            if combo_samples:
                db.save_combo_cache(pp_name, combo_samples, combo_maps=combo_maps)
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
        })
    results.sort(key=lambda x: x['p_hit'], reverse=True)
    for i, r in enumerate(results, 1):
        r['rank'] = i
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


@app.route('/api/prizepicks/leaderboard/upload', methods=['POST'])
def upload_leaderboard_image():
    """
    Upload PrizePicks screenshot(s); OCR parses player names and lines, then ranks by hit probability.
    
    Query params (optional):
        multi_engine: 'true' to use both pytesseract and easyocr (slower but more accurate)
        no_preprocessing: 'true' to skip image enhancement (not recommended)
    
    Supports single or multiple file upload:
        - Single: 'image' or 'file' field
        - Multiple: 'images' or 'files' field (array)
    """
    try:
        try:
            from scraper.image_parser import parse_prizepicks_image, parse_prizepicks_images_batch
        except ImportError as ie:
            return jsonify({'error': f'OCR not available: {ie}. Install pytesseract + Tesseract (see https://github.com/UB-Mannheim/tesseract/wiki) or easyocr.'}), 500

        # Get optional parameters
        multi_engine = request.args.get('multi_engine', 'false').lower() == 'true'
        use_preprocessing = request.args.get('no_preprocessing', 'false').lower() != 'true'
        
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
        
        # Parse images (returns projections + detected combo_maps from MAPS 1-2 vs MAPS 1-3)
        if len(image_bytes_list) == 1:
            projections, combo_maps = parse_prizepicks_image(image_bytes_list[0], use_preprocessing, multi_engine)
        else:
            projections, combo_maps = parse_prizepicks_images_batch(image_bytes_list, use_preprocessing, multi_engine)
        
        if not projections:
            return jsonify({
                'success': True,
                'leaderboard': [],
                'images_processed': len(image_bytes_list),
                'message': 'Could not parse any lines from the image(s). Ensure they show PrizePicks MAPS 1-2 or MAPS 1-3 Kills cards.'
            })

        results, skipped = _build_leaderboard_from_projections(projections, combo_maps=combo_maps)
        if results:
            source = 'batch_upload' if len(image_bytes_list) > 1 else 'upload'
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
            'preprocessing_used': use_preprocessing,
            'multi_engine_used': multi_engine,
            'message': f'Parsed {len(projections)} lines ({combo_label}){batch_info}; ranked {len(results)} with sufficient data. All {len(combined_leaderboard)} shown.' + (f' {skip_msg}' if skip_msg else '')
        })
    except Exception as e:
        logger.error(f"Error processing leaderboard image: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@app.route('/api/prizepicks/leaderboard/history', methods=['GET'])
def get_leaderboard_history():
    """List recent leaderboard snapshots."""
    try:
        limit = int(request.args.get('limit', 50))
        limit = min(limit, 200)
        snapshots = db.get_leaderboard_snapshots(limit=limit)
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
