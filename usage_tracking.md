# Claude Session Usage Tracking

Goal: figure out the actual session token limit by correlating tray token count with Claude.ai % used.

## Data Points

| Time (IST) | Tray Tokens | Opus / Sonnet split   | Cost ($) | Claude.ai % | Implied Limit | Notes |
|------------|-------------|-----------------------|----------|-------------|---------------|-------|
| ~10:30     | 22,868,376  | mostly Opus           | ~73.4    | 47%         | ~48.7M        | First reading |
| ~10:45     | 23,011,824  | mostly Opus           | ~73.4    | ?           | ?             | (skipped) |
| baseline   | 23,226,210  | 22.57M Op / 0.65M So  | 74.68    | ?           | ?             | Switched to Opus 4.7 |
| post-burn  | 23,279,402  | 22.63M Op / 0.65M So  | 74.92    | ?           | ?             | After ~53K Opus burn |
| @49%       | 23,443,276  | 22.79M Op / 0.65M So  | 75.40    | 49%         | ~47.8M        | Resets in 1h13m |
| @50%       | 23,648,138  | 22.90M Op / 0.74M So  | 75.99    | 50%         | ~47.3M        | Resets in 1h8m  |
| @55%       | 27,826,962  | 26.94M Op / 0.89M So  | 85.99    | 55%         | ~50.6M        | Resets: tray 22m, Claude.ai 9m (boundary mismatch) |

## Analysis (2 data points: 47% → 49%)

| Span | Δ tokens | Δ cost ($) | Δ % | Implied limit |
|------|----------|------------|-----|---------------|
| 47% → 49% | +574,900 (all Opus) | +2.02 | +2pp | tokens: 28.7M | cost: $101 |

- If the % were **purely raw tokens**: 574K tokens for 2% → total limit ≈ 28.7M (way below the 23M we already used → impossible).
- If the % were **purely cost-based**: $2.02 for 2% → total budget ≈ $101.
- Cumulative implied limit at 47%: 22.87M / 0.47 ≈ 48.7M tokens
- Cumulative implied limit at 49%: 23.44M / 0.49 ≈ 47.8M tokens

→ **Cumulative implied "limit" is fairly stable (~48M)** but the **marginal rate during Opus-only usage is much higher** than that average. Suggests:
  - Opus is weighted heavier than the cumulative-average token cost
  - Or the % is closer to a **cost/credit** budget than raw tokens
  - The starting baseline (~23M tokens, $74) already had a heavy Opus skew, so cumulative ≈ marginal — need a Sonnet-only burn to disambiguate.

## Next experiment
Switch to Sonnet 4.6 and burn a similar number of tokens. If %:
- **Doesn't move much** → confirmed weighted by cost (Opus 5x Sonnet)
- **Moves ~same as Opus** → it's raw tokens (rounding noise explains drift)

## Formula
Implied Limit = Tray Tokens ÷ (Claude.ai % / 100)

## Observations
- Anthropic does NOT publish exact limits
- % may be weighted (Opus costs more than Sonnet), not raw token count
- Need more data points at different % levels to confirm

## To Do
- Keep logging (tokens, %) pairs as session progresses
- Check if implied limit stays consistent → confirms raw token limit
- Check if implied limit changes → confirms weighted credit system
