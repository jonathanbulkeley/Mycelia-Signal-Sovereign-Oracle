# Mycelia Signal MCP Server

Model Context Protocol server for [Mycelia Signal](https://myceliasignal.com) — a sovereign cryptographic oracle serving 131 signed endpoints across crypto, FX, metals, economic indicators, commodities, gas oracles, volatility/sentiment/stress/contagion indices, marine, weather, DeFi yield, and COT positioning.

## Install

```bash
pip install fastmcp pynacl
```

## Run

```bash
python slo_mcp_server.py
```

Or add to Claude Desktop config (`claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "mycelia-signal": {
      "command": "python",
      "args": ["/path/to/slo_mcp_server.py"]
    }
  }
}
```

## Tools (17 parameterized tools → 131 endpoints)

| Tool | Description | Cost |
|------|-------------|------|
| `get_price(base, quote)` | Spot price for any pair | $0.01 |
| `get_vwap(base, quote)` | 5-min VWAP | $0.02 |
| `get_volatility(base, quote)` | MSVI volatility index | $0.05 |
| `get_sentiment(base, quote)` | MSXI sentiment index | $0.05 |
| `get_stress()` | MSSI market stress index | $0.05 |
| `get_contagion()` | MSTI crypto-TradFi contagion | $0.05 |
| `get_gas(chain)` | L1/L2 gas prices | $0.01 |
| `get_econ(region, indicator)` | US/EU economic data | $0.10 |
| `get_commodity(name)` | Commodities (WTI, Brent, etc.) | $0.10 |
| `get_cot(asset)` | CME COT positioning | $0.10 |
| `get_marine_sea_state(lat, lon)` | Sea state data | $0.10 |
| `get_weather(metric, lat, lon, window)` | Parametric weather | $0.10 |
| `get_defi_yield()` | DeFi protocol yields | $0.05 |
| `get_funding(base, quote)` | 10-exchange funding rates | $0.05 |
| `get_basis(base, quote)` | Cross-exchange basis | $0.02 |
| `get_open_interest(base, quote)` | Aggregated OI | $0.01 |
| `get_price_preview(base, quote)` | Unsigned sample data | **Free** |
| `get_health()` | API health check | **Free** |

## Payment

x402 (USDC on Base). No API keys. No subscriptions. Every response is Ed25519 signed and independently verifiable.

## Links

- [API Docs](https://myceliasignal.com/docs/)
- [OpenAPI Spec](https://api.myceliasignal.com/openapi.json)
- [LangChain Toolkit](https://github.com/jonathanbulkeley/langchain-mycelia-signal)
- [llms.txt](https://api.myceliasignal.com/llms.txt)
