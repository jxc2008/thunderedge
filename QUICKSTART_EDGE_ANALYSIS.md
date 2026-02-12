# Quick Start: Mathematical Edge Analysis

## Access the Edge Analysis Page

1. **Start the server:**
   ```bash
   python run.py
   ```

2. **Open in browser:**
   ```
   http://localhost:5000/edge
   ```

## Example Usage

### Example 1: Analyze "yay" at 18.5 kills

**Input:**
- Player: `yay`
- Kill Line: `18.5`
- Over Odds: `-110`
- Under Odds: `-110`

**Expected Result:**
- ✅ **BET UNDER** with +23.28% ROI
- Model mean: 16.8 kills (based on 38 maps)
- Market implied mean: 19.0 kills
- Your model is less bullish → UNDER has value

### Example 2: Check any player

Try these popular players:
- `aspas` (MIBR)
- `demon1` (NRG)
- `Less` (LOUD)
- `Zekken` (Sentinels)

## Reading the Results

### Recommendation Card
- **🟢 BET OVER** - Model thinks Over is +EV
- **🔴 BET UNDER** - Model thinks Under is +EV
- **⚪ NO BET** - Both sides are -EV (skip this prop)

### Confidence Badges
- **HIGH** (≥25 maps) - Trust the recommendation
- **MED** (10-24 maps) - Use with caution
- **LOW** (<10 maps) - Not enough data, avoid betting

### Key Metrics

**ROI (Return on Investment):**
- `+23.28%` means you expect to profit $23.28 per $100 bet
- Positive = good bet, Negative = bad bet

**Probability Edge:**
- Difference between your model and market
- `+14.57%` means your model gives 14.57% higher chance than market

**Expected Value (EV):**
- Average profit per $1 bet
- `$0.2328` means profit 23 cents per dollar bet

## The Chart Explained

**Blue Line:** Your model's kill distribution
**Orange Line:** Market's implied distribution
**Green Dashed Line:** The betting line

- If distributions overlap → market agrees with you
- If blue is left of orange → you're less bullish (UNDER value)
- If blue is right of orange → you're more bullish (OVER value)

## When to Bet

✅ **DO BET when:**
- Positive ROI (>0%)
- HIGH or MED confidence
- Large probability edge (>5%)
- You trust your cached data is current

❌ **DON'T BET when:**
- Negative ROI (<0%)
- LOW confidence
- Small edge (<2%)
- Player hasn't played recently (stale data)

## Tips for Best Results

1. **Check sample size:** More maps = better predictions
2. **Consider recency:** Is the data from recent games?
3. **Map context:** Different maps may have different kill rates
4. **Opponent strength:** Weak opponents = inflated kill numbers
5. **Role changes:** Has player switched roles recently?

## Common Questions

**Q: Why does it recommend NO BET sometimes?**
A: When both Over and Under have negative EV, you'd lose money either way.

**Q: Can I adjust the odds?**
A: Yes! Enter any American odds (e.g., -120, +110) to see updated analysis.

**Q: What if my model disagrees with market by a lot?**
A: Large disagreements could mean:
- You found real value (good!)
- Your data is stale/wrong (bad!)
- Market knows something you don't (risky!)

**Q: How is this different from regular over/under analysis?**
A: This compares against actual market prices (odds), not just historical hit rates.

## API Usage (for developers)

```bash
# Get edge analysis
curl "http://localhost:5000/api/edge/yay?line=18.5&over_odds=-110&under_odds=-110"

# Limit to last 30 maps
curl "http://localhost:5000/api/edge/yay?line=18.5&over_odds=-110&under_odds=-110&last_n=30"
```

## Verification Script

Test the math with real data:

```bash
python scripts/verify_edge_math.py
```

This runs the full analysis for multiple test cases and shows detailed calculations.

## Need Help?

See `EDGE_ANALYSIS_IMPLEMENTATION.md` for complete technical documentation.
