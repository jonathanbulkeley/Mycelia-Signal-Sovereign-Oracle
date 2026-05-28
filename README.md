# Mycelia Signal — Sovereign Oracle

Pay USDC. Get signed data. Trust math, not middlemen.

Mycelia Signal is a sovereign cryptographic oracle serving Ed25519-signed attestations across 131 endpoints: crypto prices, FX rates, precious metals, stablecoin pegs, economic indicators, commodities, gas oracles, volatility/sentiment/stress/contagion indices, marine oracle, weather oracle, DeFi yield, and CME COT positioning. Pay-per-query via x402 (USDC on Base). No API keys. No accounts. No trust assumptions.

**Live API:** [api.myceliasignal.com](https://api.myceliasignal.com)
**Docs:** [myceliasignal.com/docs](https://myceliasignal.com/docs)
**OpenAPI:** [api.myceliasignal.com/openapi.json](https://api.myceliasignal.com/openapi.json)
**llms.txt:** [api.myceliasignal.com/llms.txt](https://api.myceliasignal.com/llms.txt)

---

## Try It Now

    # Free preview
    curl https://api.myceliasignal.com/oracle/price/btc/usd/preview
    curl https://api.myceliasignal.com/oracle/stress/market/preview

    # Paid — returns 402 with x402 payment details
    curl -i https://api.myceliasignal.com/oracle/price/btc/usd

    # Health check
    curl https://api.myceliasignal.com/health

---

## Endpoints (131 total)

All paid endpoints return Ed25519-signed canonical attestations. Append `/preview` for free unsigned sample data.

### Crypto Prices (16) — $0.01 spot / $0.02 VWAP
BTC, ETH, SOL, XRP, ADA, DOGE in USD/EUR/JPY. VWAP for BTC and ETH.

### Stablecoin Pegs (4) — $0.01
USDT/USD, USDC/USD, USDT/EUR, USDT/JPY.

### Precious Metals (3) — $0.01
XAU/USD, XAU/EUR, XAU/JPY.

### FX Rates (19) — $0.01
Major and cross pairs: EUR, GBP, USD, CHF, CNY, CAD, JPY.

### Gas Oracles (6) — $0.01
Ethereum, Polygon, Arbitrum, Optimism, Base, Solana.

### Indices — $0.05 each

| Index | Description | Range |
|-------|-------------|-------|
| **MSVI** (Volatility) | 5-component: realized vol, implied vol, term structure, funding, put/call | 0-100 |
| **MSXI** (Sentiment) | 5-component: funding direction, skew, put/call, term structure, basis | -100 to +100 |
| **MSSI** (Stress) | 4-component: vol regime, stablecoin stress, funding extremity, dispersion | 0-100 |
| **MSTI** (Contagion) | 4-component: BTC-equity correlation, equity vol, DXY, beta | 0-100 |

### MSFR Funding Rate — $0.05
10-exchange OI-weighted composite (Binance, Bybit, OKX, Deribit, Hyperliquid, dYdX, Bitget, Kraken, Coinbase INTX, Crypto.com). Basis and OI also available.

### Economic Indicators — $0.10
US (8): CPI, CPI Core, Unemployment, NFP, Fed Funds, GDP, PCE, Yield Curve.
EU (6): HICP, HICP Core, HICP Services, Unemployment, GDP, Employment.

### Commodities (5) — $0.10
WTI, Brent, Natural Gas, Copper, DXY.

### Marine Oracle — $0.10
Sea state, vessel tracking (AIS), voyage forecast.

### Weather Oracle — $0.10
Parametric temperature, rainfall, wind, drought for any coordinates.

### DeFi Yield — $0.05
Cross-protocol yield data.

### CME COT — $0.10
Institutional positioning from CME futures.

### DLC Oracle — Free
Discreet Log Contract attestations.

---

## MCP Server

17 parameterized tools covering all 131 endpoints. See [mcp/](./mcp/).

Claude Desktop config:

    {
      "mcpServers": {
        "mycelia-signal": {
          "command": "python",
          "args": ["myceliasignal_mcp_server.py"],
          "env": {}
        }
      }
    }

Install and run:

    pip install fastmcp pynacl
    python mcp/myceliasignal_mcp_server.py

---

## Integrations

- **MCP Server:** [mcp/](./mcp/) — 17 tools, Python + FastMCP
- **LangChain:** [langchain-mycelia-signal](https://github.com/jonathanbulkeley/langchain-mycelia-signal) — PyPI, 17 tools
- **OpenAPI:** [openapi.json](https://api.myceliasignal.com/openapi.json)
- **Agent Discovery:** [agent.json](https://api.myceliasignal.com/.well-known/agent.json), [agent-card.json](https://api.myceliasignal.com/.well-known/agent-card.json)
- **x402 Discovery:** [.well-known/x402](https://api.myceliasignal.com/.well-known/x402)

---

## Verification

Every response includes an Ed25519 signature over a canonical attestation string:

    v1|PRICE|BTCUSD|73242.09|USD|2|binance,coinbase,kraken,...|median|1748012345|562204

Verify with the public key from `/health`. See [docs/verification](https://myceliasignal.com/docs/verification/).

---

## License

MIT
