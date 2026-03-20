# Token Spend Simulation Logic

## Purpose
Simulate and compare the cost of running local LLM inference (token-based) versus calling a premium external API (e.g., OpenAI, Anthropic) for a similar model type.

---

## Local LLM (Power-Based Cost)
- **Assumptions:**
  - Model: 20B parameters, 64K context window
  - Power draw: 250W (typical for RTX 3090 under load)
  - National average electricity cost: $0.10/kWh
  - Inference time: 1,000 tokens in 30 seconds (0.0083 hours)
- **Calculation:**
  - Energy used: 250W × 0.0083h = 2.08 Wh = 0.00208 kWh
  - Local cost: 0.00208 kWh × $0.10 = $0.000208 per 1,000 tokens

---

## Premium API (External Call)
- **Example Pricing:**
  - OpenAI GPT-4o: $5.00 per 1M tokens ($0.005 per 1,000 tokens)
  - Anthropic Claude 3 Opus: $15.00 per 1M tokens ($0.015 per 1,000 tokens)
- **API cost per 1,000 tokens:** $0.005–$0.015

---

## Comparison Table
| Source         | Cost per 1,000 tokens |
|---------------|----------------------|
| Local LLM     | $0.0002              |
| OpenAI GPT-4o | $0.005               |
| Claude 3 Opus | $0.015               |

---

## Headline Insight
> "Running a 20B parameter LLM locally costs less than 1/20th of a cent per 1,000 tokens—over 20x cheaper than premium API calls."

---

## Why This Matters
- Empowers users to understand and optimize their AI spend
- Makes the value of local inference transparent
- Drives adoption of local, power-efficient LLMs

---

## Next Steps
- Integrate this logic into the Value-Add dashboard and site headline
- Update calculations as hardware and API pricing evolve
