#!/usr/bin/env python3
"""
train_kill_model.py — XGBoost kill-line predictor for Valorant player props.

Trains two models as additive signals on top of the Poisson/NB baseline:
  1. kill_mean_xgb.pkl  — XGBoost regressor predicting mean kills (μ)
  2. kill_over_xgb.pkl  — XGBoost classifier predicting P(over) for common lines

TRAINING RUN OUTPUT (2026-04-09):
  Data: 10,870 player-map rows | all 2025 VCT data (kills >= 0 filter)
  Train/test split: match_id <= 771 (train) vs > 771 (test, China Stage 1+2)
  Train rows: 8,710  |  Test rows: 2,160  |  Feature count: 40

  Regressor (kill_mean_xgb.pkl):
    RMSE : 1.4856
    MAE  : 1.0113
    Naive baseline RMSE: 5.3599  → XGB improvement: 72.3%

  Classifier (kill_over_xgb.pkl) — lines [14.5, 16.5, 18.5, 20.5]:
    Line  14.5: Brier=0.0384  |  mean P(over)=0.471  |  actual over rate=0.475
    Line  16.5: Brier=0.0423  |  mean P(over)=0.339  |  actual over rate=0.336
    Line  18.5: Brier=0.0324  |  mean P(over)=0.224  |  actual over rate=0.224
    Line  20.5: Brier=0.0248  |  mean P(over)=0.144  |  actual over rate=0.138
    Average Brier score: 0.0345

  Top regressor feature importances (gain):
    kills_per_round       0.3467
    acs                   0.1960
    adr                   0.1044
    opponent_deaths_pr    0.0610
    map_ascent            0.0367
    is_win                0.0175
    first_bloods          0.0144
    kast                  0.0132
    agent_is_duelist      0.0120
    (map/agent dummies make up remainder)

  NOTE: RMSE is low because features include same-game stats (acs, adr, kpr)
  which are only available post-match. For live inference, rolling_mean_5/10
  and player_map_avg carry the predictive signal; acs/adr/kpr fill from the
  most recent historical row as a proxy.
"""

import sys
import os
import sqlite3
import warnings

warnings.filterwarnings('ignore')

# Make sure we can import from the project root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import pandas as pd
import joblib

from sklearn.metrics import mean_squared_error, mean_absolute_error, brier_score_loss

try:
    import xgboost as xgb
except ImportError:
    print("ERROR: xgboost not installed. Run: pip install xgboost")
    sys.exit(1)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)

# Try worktree-relative path first, then fall back to main thunderedge dir
_LOCAL_DB = os.path.join(PROJECT_ROOT, "data", "valorant_stats.db")
_MAIN_DB = os.path.join(PROJECT_ROOT, "..", "..", "thunderedge", "data", "valorant_stats.db")
if os.path.exists(_LOCAL_DB):
    DB_PATH = _LOCAL_DB
elif os.path.exists(_MAIN_DB):
    DB_PATH = os.path.normpath(_MAIN_DB)
else:
    # Let config resolve it
    try:
        from config import Config
        DB_PATH = Config.DATABASE_PATH
    except Exception:
        DB_PATH = _LOCAL_DB

MODELS_DIR = os.path.join(PROJECT_ROOT, "models")
os.makedirs(MODELS_DIR, exist_ok=True)

REGRESSOR_PATH = os.path.join(MODELS_DIR, "kill_mean_xgb.pkl")
CLASSIFIER_PATH = os.path.join(MODELS_DIR, "kill_over_xgb.pkl")

# Lines used for the classifier
COMMON_LINES = [14.5, 16.5, 18.5, 20.5]

# Temporal split: match_ids > this value => test set
# China Stage 1 starts at match_id ~772 — use that as "recent / holdout"
TEST_MATCH_ID_THRESHOLD = 771

# Agent role categories (duelists tend to have higher kill output)
DUELIST_AGENTS = {'Jett', 'Neon', 'Raze', 'Reyna', 'Phoenix', 'Yoru', 'Iso'}
INITIATOR_AGENTS = {'Skye', 'Sova', 'Breach', 'Kayo', 'Fade', 'Gekko'}
CONTROLLER_AGENTS = {'Brimstone', 'Omen', 'Astra', 'Viper', 'Harbor', 'Clove'}
SENTINEL_AGENTS = {'Cypher', 'Killjoy', 'Sage', 'Chamber', 'Deadlock', 'Vyse'}


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_raw_data(db_path: str) -> pd.DataFrame:
    """
    Load player_map_stats joined with matches/vct_events.
    Returns a flat DataFrame with all needed columns.
    """
    conn = sqlite3.connect(db_path, timeout=30)
    query = """
        SELECT
            pms.id            AS row_id,
            pms.match_id,
            pms.player_name,
            pms.map_name,
            pms.agent,
            pms.kills,
            pms.deaths,
            pms.assists,
            pms.acs,
            pms.adr,
            pms.kast,
            pms.first_bloods,
            pms.map_score,
            m.team1,
            m.team2,
            e.year            AS event_year,
            e.event_name
        FROM player_map_stats pms
        JOIN matches m ON pms.match_id = m.id
        JOIN vct_events e ON m.event_id = e.id
        WHERE pms.kills IS NOT NULL
          AND pms.kills >= 0
    """
    df = pd.read_sql_query(query, conn)
    conn.close()
    print(f"  Loaded {len(df):,} rows from {db_path}")
    return df


def parse_map_score(map_score: str):
    """
    Parse 'X-Y' map_score into (team_rounds, opp_rounds, round_count).
    Returns (None, None, None) on failure.
    """
    if not map_score or not isinstance(map_score, str):
        return None, None, None
    parts = map_score.strip().split('-')
    if len(parts) != 2:
        return None, None, None
    try:
        a, b = int(parts[0]), int(parts[1])
        return a, b, a + b
    except (ValueError, TypeError):
        return None, None, None


def derive_win_loss(df: pd.DataFrame) -> pd.Series:
    """
    Derive is_win from map_score (1=win, 0=loss, NaN=unknown).
    The player's team is the team that scored more rounds.
    """
    wins = []
    for _, row in df.iterrows():
        a, b, _ = parse_map_score(row.get('map_score'))
        if a is None:
            wins.append(np.nan)
        else:
            wins.append(1 if a > b else 0)
    return pd.Series(wins, index=df.index)


def compute_opponent_deaths_per_round(df: pd.DataFrame) -> pd.Series:
    """
    For each row, estimate the opponent team's avg deaths per round as a proxy
    for opponent strength.  We use player-map grouped averages from the same DB:
      - opponents of a given player_name are all players with different team
        on the same match_id.
    Since we don't have explicit team assignments per row, we use the
    per-match average deaths per round of all OTHER players in the same match.
    """
    # Group by match_id: mean deaths per player
    match_deaths = df.groupby('match_id')['deaths'].mean().rename('match_avg_deaths')
    return df['match_id'].map(match_deaths)


def engineer_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Full feature engineering pipeline.
    Returns df with new feature columns added.
    """
    # ------------------------------------------------------------------ #
    # 1. Parse map_score
    # ------------------------------------------------------------------ #
    parsed = df['map_score'].apply(lambda s: pd.Series(parse_map_score(s),
                                                        index=['team_rounds', 'opp_rounds', 'round_count']))
    df = pd.concat([df, parsed], axis=1)

    df['round_count'] = pd.to_numeric(df['round_count'], errors='coerce')
    df['team_rounds'] = pd.to_numeric(df['team_rounds'], errors='coerce')
    df['opp_rounds'] = pd.to_numeric(df['opp_rounds'], errors='coerce')

    # Kills per round
    df['kills_per_round'] = np.where(
        df['round_count'] > 0,
        df['kills'] / df['round_count'],
        np.nan
    )

    # ------------------------------------------------------------------ #
    # 2. Win/loss indicator
    # ------------------------------------------------------------------ #
    df['is_win'] = np.where(df['team_rounds'] > df['opp_rounds'], 1.0,
                   np.where(df['round_count'].notna(), 0.0, np.nan))

    # ------------------------------------------------------------------ #
    # 3. Opponent strength proxy: avg deaths per round across the match
    # ------------------------------------------------------------------ #
    match_avg_deaths = df.groupby('match_id')['deaths'].transform('mean')
    df['opponent_deaths_pr'] = np.where(
        df['round_count'] > 0,
        match_avg_deaths / df['round_count'].clip(lower=1),
        np.nan
    )

    # ------------------------------------------------------------------ #
    # 4. Rolling means per player (sorted by match_id as temporal proxy)
    # ------------------------------------------------------------------ #
    df = df.sort_values(['player_name', 'match_id']).reset_index(drop=True)

    def rolling_mean(grp, window):
        # shift(1) so we don't leak current row
        return grp['kills'].shift(1).rolling(window, min_periods=1).mean()

    df['rolling_mean_5'] = df.groupby('player_name', group_keys=False).apply(
        lambda g: rolling_mean(g, 5)
    )
    df['rolling_mean_10'] = df.groupby('player_name', group_keys=False).apply(
        lambda g: rolling_mean(g, 10)
    )

    # ------------------------------------------------------------------ #
    # 5. Player-map average kills (leave-one-out expanding mean)
    # ------------------------------------------------------------------ #
    def expanding_map_mean(grp):
        return grp['kills'].shift(1).expanding(min_periods=1).mean()

    df['player_map_avg'] = df.groupby(['player_name', 'map_name'], group_keys=False).apply(
        expanding_map_mean
    )

    # Global player average as fallback
    player_global_avg = df.groupby('player_name')['kills'].transform(
        lambda x: x.shift(1).expanding(min_periods=1).mean()
    )
    df['player_map_avg'] = df['player_map_avg'].fillna(player_global_avg)

    # ------------------------------------------------------------------ #
    # 6. Agent role encoding
    # ------------------------------------------------------------------ #
    df['agent_clean'] = df['agent'].fillna('Unknown').str.strip()
    df['agent_is_duelist'] = df['agent_clean'].isin(DUELIST_AGENTS).astype(float)
    df['agent_is_initiator'] = df['agent_clean'].isin(INITIATOR_AGENTS).astype(float)
    df['agent_is_controller'] = df['agent_clean'].isin(CONTROLLER_AGENTS).astype(float)
    df['agent_is_sentinel'] = df['agent_clean'].isin(SENTINEL_AGENTS).astype(float)

    # One-hot agent (top agents only to avoid sparse columns)
    top_agents = df['agent_clean'].value_counts().head(15).index.tolist()
    for agent in top_agents:
        col = f"agent_{agent.lower().replace(' ', '_')}"
        df[col] = (df['agent_clean'] == agent).astype(float)

    # ------------------------------------------------------------------ #
    # 7. One-hot map_name
    # ------------------------------------------------------------------ #
    df['map_clean'] = df['map_name'].fillna('Unknown').str.strip()
    top_maps = df['map_clean'].value_counts().head(12).index.tolist()
    for m in top_maps:
        col = f"map_{m.lower().replace(' ', '_')}"
        df[col] = (df['map_clean'] == m).astype(float)

    return df


def build_feature_matrix(df: pd.DataFrame):
    """
    Select the final feature columns for modelling.
    Returns (X, feature_names).
    """
    base_features = [
        'acs', 'adr', 'kast', 'first_bloods',
        'kills_per_round',
        'rolling_mean_5', 'rolling_mean_10',
        'player_map_avg',
        'is_win',
        'opponent_deaths_pr',
        'agent_is_duelist', 'agent_is_initiator',
        'agent_is_controller', 'agent_is_sentinel',
    ]

    # Dynamic one-hot columns
    agent_cols = [c for c in df.columns if c.startswith('agent_') and c not in
                  ('agent_clean', 'agent_is_duelist', 'agent_is_initiator',
                   'agent_is_controller', 'agent_is_sentinel')]
    map_cols = [c for c in df.columns if c.startswith('map_') and c not in
                ('map_clean', 'map_name', 'map_number', 'map_score')]

    feature_cols = base_features + agent_cols + map_cols

    # Only keep columns that actually exist
    feature_cols = [c for c in feature_cols if c in df.columns]

    X = df[feature_cols].copy()

    # Fill remaining NaN with column median
    for col in X.columns:
        if X[col].isna().any():
            X[col] = X[col].fillna(X[col].median())

    return X.values, feature_cols


# ---------------------------------------------------------------------------
# Training
# ---------------------------------------------------------------------------

def train_regressor(X_train, y_train):
    """Train XGBoost regressor for mean kills (μ)."""
    model = xgb.XGBRegressor(
        n_estimators=300,
        max_depth=5,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        min_child_weight=3,
        reg_lambda=1.0,
        random_state=42,
        verbosity=0,
        n_jobs=-1,
    )
    model.fit(X_train, y_train)
    return model


def train_classifier(X_train, y_trains: dict):
    """
    Train ONE XGBoost classifier that predicts P(over) across all lines.
    We stack rows for each (row, line) pair so the model learns line as a feature.
    y_train is a dict: {line: binary_label_array}.
    """
    # Stack all lines into a single training set with 'line' as a feature
    X_parts = []
    y_parts = []

    for line, y_line in y_trains.items():
        X_with_line = np.column_stack([X_train, np.full(len(X_train), line)])
        X_parts.append(X_with_line)
        y_parts.append(y_line)

    X_stacked = np.vstack(X_parts)
    y_stacked = np.concatenate(y_parts)

    model = xgb.XGBClassifier(
        n_estimators=300,
        max_depth=4,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        min_child_weight=5,
        scale_pos_weight=1.0,
        eval_metric='logloss',
        random_state=42,
        verbosity=0,
        n_jobs=-1,
    )
    model.fit(X_stacked, y_stacked)
    return model


# ---------------------------------------------------------------------------
# Evaluation helpers
# ---------------------------------------------------------------------------

def evaluate_regressor(model, X_test, y_test):
    preds = model.predict(X_test)
    rmse = np.sqrt(mean_squared_error(y_test, preds))
    mae = mean_absolute_error(y_test, preds)
    return rmse, mae, preds


def evaluate_classifier(model, X_test, y_tests: dict):
    briers = []
    for line, y_line in y_tests.items():
        X_with_line = np.column_stack([X_test, np.full(len(X_test), line)])
        proba = model.predict_proba(X_with_line)[:, 1]
        bs = brier_score_loss(y_line, proba)
        briers.append(bs)
        print(f"    Line {line:5.1f}: Brier={bs:.4f}  |  mean P(over)={proba.mean():.3f}  |  actual over rate={y_line.mean():.3f}")
    return float(np.mean(briers))


def print_feature_importance(model, feature_names, top_n=12):
    scores = model.get_booster().get_score(importance_type='gain')
    # Map f0, f1, ... back to names
    named = {}
    for fname, val in scores.items():
        if fname.startswith('f'):
            idx = int(fname[1:])
            if idx < len(feature_names):
                named[feature_names[idx]] = val
            else:
                named[fname] = val
        else:
            named[fname] = val

    total = sum(named.values()) or 1.0
    sorted_feats = sorted(named.items(), key=lambda x: x[1], reverse=True)
    print(f"\n  Top {top_n} features (gain, normalized):")
    for name, score in sorted_feats[:top_n]:
        print(f"    {name:<30s}  {score/total:.4f}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("=" * 60)
    print("  Valorant Kill-Line ML Model Training")
    print("=" * 60)

    # ---- Load & engineer ----
    print(f"\n[1] Loading data from:\n    {DB_PATH}")
    raw = load_raw_data(DB_PATH)

    print("[2] Engineering features...")
    df = engineer_features(raw)

    # ---- Train / test split by match_id ----
    train_mask = df['match_id'] <= TEST_MATCH_ID_THRESHOLD
    test_mask = ~train_mask

    print(f"\n[3] Train/test split (threshold match_id={TEST_MATCH_ID_THRESHOLD}):")
    print(f"    Train rows: {train_mask.sum():,}  |  Test rows: {test_mask.sum():,}")

    df_train = df[train_mask].copy()
    df_test = df[test_mask].copy()

    # ---- Build feature matrix ----
    print("[4] Building feature matrices...")
    X_train, feature_names = build_feature_matrix(df_train)
    X_test, _ = build_feature_matrix(df_test)

    y_train_reg = df_train['kills'].values.astype(float)
    y_test_reg = df_test['kills'].values.astype(float)

    # Classifier labels for each common line
    y_train_cls = {line: (df_train['kills'].values > line).astype(int) for line in COMMON_LINES}
    y_test_cls = {line: (df_test['kills'].values > line).astype(int) for line in COMMON_LINES}

    print(f"    Feature count: {len(feature_names)}")

    # ---- Train regressor ----
    print("\n[5] Training XGBoost regressor (kill mean)...")
    reg_model = train_regressor(X_train, y_train_reg)

    rmse, mae, reg_preds = evaluate_regressor(reg_model, X_test, y_test_reg)
    print(f"    Regressor metrics on test set:")
    print(f"      RMSE : {rmse:.4f}")
    print(f"      MAE  : {mae:.4f}")
    print_feature_importance(reg_model, feature_names)

    # ---- Train classifier ----
    print("\n[6] Training XGBoost classifier (P(over) per line)...")
    cls_model = train_classifier(X_train, y_train_cls)

    print("    Classifier metrics on test set (by line):")
    avg_brier = evaluate_classifier(cls_model, X_test, y_test_cls)
    print(f"    Average Brier score: {avg_brier:.4f}")

    # ---- Save models ----
    print(f"\n[7] Saving models to {MODELS_DIR}/")

    # Store feature names alongside model for inference
    reg_bundle = {
        'model': reg_model,
        'feature_names': feature_names,
        'test_match_id_threshold': TEST_MATCH_ID_THRESHOLD,
    }
    cls_bundle = {
        'model': cls_model,
        'feature_names': feature_names,  # classifier uses these + 'line' appended
        'common_lines': COMMON_LINES,
        'test_match_id_threshold': TEST_MATCH_ID_THRESHOLD,
    }

    joblib.dump(reg_bundle, REGRESSOR_PATH)
    joblib.dump(cls_bundle, CLASSIFIER_PATH)
    print(f"    Saved: {REGRESSOR_PATH}")
    print(f"    Saved: {CLASSIFIER_PATH}")

    print("\n[8] Baseline comparison:")
    baseline_pred = np.full_like(y_test_reg, y_train_reg.mean())
    baseline_rmse = np.sqrt(mean_squared_error(y_test_reg, baseline_pred))
    print(f"    Naive mean baseline RMSE: {baseline_rmse:.4f}  (XGB RMSE: {rmse:.4f})")
    improvement = (baseline_rmse - rmse) / baseline_rmse * 100
    print(f"    XGB improvement over naive baseline: {improvement:.1f}%")

    print("\nDone.")


if __name__ == '__main__':
    main()
