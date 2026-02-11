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
from scraper.team_scraper import TeamScraper
from scraper.team_processor import TeamProcessor
from backend.database import Database
from backend.model_params import get_player_distribution
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
    """Get PrizePicks analysis for a specific player"""
    try:
        # Get kill line from query params (default to 30.5 for combined maps 1+2)
        kill_line = float(request.args.get('line', 30.5))
        
        # Create processor with specified kill line
        processor = PrizePicksProcessor(kill_line=kill_line)
        
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

# Add error handler for 404 to debug (at end of file, after all routes)
@app.errorhandler(404)
def handle_404(e):
    logger.error(f"404 Not Found: {request.path}")
    return jsonify({'error': 'Not Found', 'path': request.path}), 404

if __name__ == '__main__':
    app.run(debug=True, port=5000)
