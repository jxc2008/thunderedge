# Valorant KPR Betting Analysis Tool

A web scraping tool that analyzes Valorant player statistics from VLR.gg to evaluate betting lines for Kills Per Round (KPR).

## Project Structure

```
valorant-kpr-tracker/
├── scraper/
│   ├── __init__.py
│   ├── vlr_scraper.py      # Web scraper for VLR.gg
│   └── player_processor.py  # KPR analysis and predictions
├── backend/
│   ├── __init__.py
│   ├── api.py              # Flask REST API
│   ├── calculator.py       # Advanced KPR calculations
│   └── database.py         # SQLite database handler
├── frontend/
│   ├── app.py              # Alternative frontend entry
│   └── templates/
│       └── index.html      # Web interface
├── data/                   # Database storage
├── config.py               # Configuration settings
├── requirements.txt        # Python dependencies
├── run.py                  # Main application entry
└── README.md
```

## Installation

1. Install Python dependencies:
```bash
pip install -r requirements.txt
```

2. Run the application:
```bash
python run.py
```

3. Open your browser to http://localhost:5000

## API Endpoints

### GET /api/player/{IGN}
Analyze a single player's KPR statistics.

**Query Parameters:**
- `line` (optional): Betting line KPR (default: 0.70)

**Example:**
```
GET /api/player/TenZ?line=0.75
```

### POST /api/batch
Analyze multiple players at once.

**Request Body:**
```json
{
    "players": ["TenZ", "aspas", "demon1"],
    "line": 0.70
}
```

### GET /api/stats
Get system statistics (tracked players, events recorded).

## How It Works

1. **Web Scraping**: The tool scrapes player statistics from VLR.gg in real-time
2. **Data Processing**: Historical KPR data is analyzed for trends and patterns
3. **Prediction**: A weighted algorithm predicts expected KPR
4. **Evaluation**: The prediction is compared against the betting line
5. **Classification**: Results are classified as UNDERPRICED, OVERPRICED, or FAIR VALUE

## Prediction Formula

```
predicted_kpr = (0.6 * average_kpr) + (0.4 * recent_kpr) + (0.1 * trend)
```

## Classification Thresholds

- **UNDERPRICED HIGH**: Predicted KPR is 10%+ above the line
- **UNDERPRICED MEDIUM**: Predicted KPR is 5-10% above the line
- **OVERPRICED HIGH**: Predicted KPR is 10%+ below the line
- **OVERPRICED MEDIUM**: Predicted KPR is 5-10% below the line
- **FAIR VALUE**: Within 5% of the betting line

## Important Notes

### Web Scraping Ethics
- Check VLR.gg's robots.txt and terms of service
- The scraper includes delays between requests
- Results are cached to avoid excessive requests

### Legal Disclaimer
- This tool is for educational/prototyping purposes only
- Not financial or betting advice
- Check local laws regarding sports betting data

## License

MIT License
