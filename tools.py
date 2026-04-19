"""
Tool registry: maps tool names to API endpoint metadata and parameter schemas.
The LLM planner sees these schemas to decide which tools to call.
"""

TOOLS = {
    # =========================================================================
    # SRC Service (/cr/src)
    # =========================================================================
    "search_funds": {
        "description": (
            "Search for mutual funds using natural language. "
            "Examples: 'low expense ratio large cap funds', 'top performing mid cap funds', "
            "'SBI funds with high returns'. "
            "Returns ranked fund recommendations with fund names, ISINs, and key metrics. "
            "Use this for discovering new funds — NOT for analyzing an existing portfolio."
        ),
        "endpoint": "/cr/src/get_query_data",
        "method": "POST",
        "parameters": {
            "query": {
                "type": "string",
                "required": True,
                "description": "Natural language fund search query",
            },
            "query_type": {
                "type": "string",
                "required": True,
                "description": "Type of query: 'fund_discovery', 'fund_comparison', etc.",
                "default": "fund_discovery",
            },
            "num_results": {
                "type": "integer",
                "required": False,
                "description": "Number of results to return",
                "default": 3,
            },
            "plan_type": {
                "type": "string",
                "required": False,
                "description": "Fund plan type",
                "enum": ["regular", "direct"],
                "default": "direct",
            },
            "org_id": {
                "type": "string",
                "required": False,
                "description": "Organization ID for context",
            },
        },
    },
    "swap_recommendations": {
        "description": (
            "Get better fund alternatives for a specific fund holding. "
            "Finds funds ranked higher than the current holding based on returns, risk, or cost. "
            "Requires internal_security_id_list — use this when you already know which fund(s) "
            "the user wants to replace."
        ),
        "endpoint": "/cr/src/swap_recommendations",
        "method": "POST",
        "parameters": {
            "recommendation_type": {
                "type": "string",
                "required": True,
                "description": "Basis for recommendation",
                "enum": ["returns", "risk", "cost"],
            },
            "internal_security_id_list": {
                "type": "array",
                "required": True,
                "description": "List of internal security IDs to find alternatives for",
            },
            "cursor": {
                "type": "integer",
                "required": False,
                "description": "Pagination cursor (0 = first page)",
                "default": 0,
            },
            "org_id": {
                "type": "string",
                "required": False,
                "description": "Organization ID",
            },
        },
    },
    "portfolio_swap_recommendations": {
        "description": (
            "Analyze an entire user portfolio and generate swap recommendations "
            "for each mutual fund holding (on returns, risk, cost basis) and stock holding."
        ),
        "endpoint": "/cr/src/portfolio_swap_recommendations",
        "method": "POST",
        "parameters": {
            "user_id": {
                "type": "string",
                "required": False,
                "description": "Internal user ID",
            },
            "external_user_id": {
                "type": "string",
                "required": False,
                "description": "External user ID",
            },
            "org_id": {
                "type": "string",
                "required": True,
                "description": "Organization ID",
            },
            "top_n_recommendations": {
                "type": "integer",
                "required": False,
                "description": "Max recommendations per holding (1-10)",
                "default": 3,
            },
        },
    },
    "get_fund_peers": {
        "description": (
            "Get peer funds in the same category/benchmark for comparison. "
            "Returns peer list, percentile rankings, highlights, and category summary."
        ),
        "endpoint": "/cr/src/get_fund_peers",
        "method": "POST",
        "parameters": {
            "security_id": {
                "type": "string",
                "required": True,
                "description": "Fund identifier (ISIN or internal security ID)",
            },
            "security_id_type": {
                "type": "string",
                "required": False,
                "description": "Type of security_id",
                "enum": ["internalSecurityId", "isin"],
                "default": "internalSecurityId",
            },
            "benchmark_level": {
                "type": "integer",
                "required": False,
                "description": "Benchmark comparison level (1 or 2)",
                "default": 1,
            },
            "limit": {
                "type": "integer",
                "required": False,
                "description": "Max peers to return (1-100)",
                "default": 3,
            },
            "org_id": {
                "type": "string",
                "required": True,
                "description": "Organization ID",
            },
        },
    },
    "stock_research_data": {
        "description": (
            "Get stock research data including target prices, entry prices, stop loss, "
            "risk-reward ratio, and analyst rationale. Lookup by ISIN or internal security ID."
        ),
        "endpoint": "/cr/src/stock_research_data",
        "method": "POST",
        "parameters": {
            "ids": {
                "type": "array",
                "required": True,
                "description": "List of identifiers (ISINs or internal security IDs)",
            },
            "id_type": {
                "type": "string",
                "required": True,
                "description": "Type of identifier",
                "enum": ["isin", "internalSecurityId"],
            },
        },
    },
    "parse_query": {
        "description": (
            "Parse a natural language investment query into structured entities (NER). "
            "Returns raw parsed entities without ranking. Useful for debugging query interpretation."
        ),
        "endpoint": "/cr/src/parser",
        "method": "POST",
        "parameters": {
            "query": {
                "type": "string",
                "required": True,
                "description": "Natural language query to parse",
            },
            "query_type": {
                "type": "string",
                "required": True,
                "description": "Type of query",
                "default": "fund_discovery",
            },
        },
    },
    "can_support": {
        "description": (
            "Check if the system can handle a given query. Returns confidence score, "
            "reasoning, limitations, and recommended parameters for the actual call."
        ),
        "endpoint": "/cr/src/canSupport",
        "method": "POST",
        "parameters": {
            "query": {
                "type": "string",
                "required": True,
                "description": "Natural language query to assess",
            },
            "org_id": {
                "type": "string",
                "required": False,
                "description": "Organization ID for context-specific capabilities",
            },
        },
    },
    # =========================================================================
    # Model Portfolio Service (/cr/model-portfolio)
    # =========================================================================
    "get_portfolio_options": {
        "description": (
            "Core portfolio recommendation endpoint. Given an investment amount and type "
            "(LUMP_SUM or SIP), returns a complete model portfolio with recommended mutual funds, "
            "allocation percentages, and a historical backtest with performance metrics (CAGR, "
            "Sharpe ratio, max drawdown, 1Y/3Y/5Y returns). Also returns 5 alternative fund "
            "choices per segment for the user to swap. Portfolio style is auto-determined from "
            "the user's stored risk profile unless explicitly overridden via "
            "portfolio_risk_preference. "
            "The response ALREADY includes backtest results and performance metrics — "
            "do NOT follow up with backtest_portfolio unless the user explicitly wants to "
            "swap a fund and re-backtest."
        ),
        "endpoint": "/cr/model-portfolio/get_portfolio_options",
        "method": "POST",
        "parameters": {
            "amount": {
                "type": "integer",
                "required": True,
                "description": "Investment amount in INR",
            },
            "user_id": {
                "type": "integer",
                "required": True,
                "description": "User ID for personalization",
            },
            "portfolio_risk_preference": {
                "type": "string",
                "required": False,
                "description": "Risk preference level",
                "enum": ["VERY_LOW", "LOW", "MEDIUM", "HIGH", "VERY_HIGH"],
            },
            "investment_type": {
                "type": "string",
                "required": True,
                "description": "Investment type",
                "enum": ["LUMP_SUM", "SIP"],
            },
            "org_id": {
                "type": "string",
                "required": False,
                "description": "Organization ID",
            },
            "plan_type": {
                "type": "string",
                "required": False,
                "description": "Fund plan type",
                "enum": ["direct", "regular"],
                "default": "regular",
            },
        },
    },
    "backtest_portfolio": {
        "description": (
            "Re-run a backtest ONLY when the user has swapped a fund in the default portfolio "
            "returned by get_portfolio_options. Do NOT call this after get_portfolio_options — "
            "that response already includes backtest results. Only use this when the user "
            "explicitly wants to replace a default fund with an alternative and compare "
            "updated performance metrics. Returns updated CAGR, Sharpe ratio, max drawdown."
        ),
        "endpoint": "/cr/model-portfolio/backtest_selected_portfolio",
        "method": "POST",
        "parameters": {
            "amount": {
                "type": "integer",
                "required": True,
                "description": "Investment amount in INR",
            },
            "user_id": {
                "type": "integer",
                "required": True,
                "description": "User ID",
            },
            "portfolio_risk_preference": {
                "type": "string",
                "required": False,
                "description": "Risk preference",
                "enum": ["VERY_LOW", "LOW", "MEDIUM", "HIGH", "VERY_HIGH"],
            },
            "investment_type": {
                "type": "string",
                "required": True,
                "description": "Investment type",
                "enum": ["LUMP_SUM", "SIP"],
            },
            "org_id": {
                "type": "string",
                "required": False,
                "description": "Organization ID",
            },
            "selected_funds": {
                "type": "object",
                "required": True,
                "description": (
                    "User's custom fund selection after swapping. Keys: equity, debt, "
                    "alternatives, cash. Values: dict mapping segment name to "
                    "internal_security_id (numeric string). "
                    'Example: {"equity": {"large_cap": "3310010938"}, '
                    '"debt": {"gilt": "3310020456"}}'
                ),
            },
            "plan_type": {
                "type": "string",
                "required": False,
                "description": "Fund plan type",
                "enum": ["direct", "regular"],
                "default": "regular",
            },
        },
    },
    "portfolio_builder": {
        "description": (
            "Builds and backtests a portfolio from user-selected funds. Use this when the "
            "user has already chosen specific funds (after browsing options from "
            "get_portfolio_options). Returns portfolio with amounts allocated, performance "
            "metrics (CAGR, Sharpe ratio, max drawdown), and 1Y/3Y/5Y returns."
        ),
        "endpoint": "/cr/model-portfolio/portfolio_builder",
        "method": "POST",
        "parameters": {
            "amount": {
                "type": "integer",
                "required": True,
                "description": "Investment amount in INR",
            },
            "user_id": {
                "type": "integer",
                "required": True,
                "description": "User ID",
            },
            "portfolio_risk_preference": {
                "type": "string",
                "required": False,
                "description": "Risk preference",
            },
            "investment_type": {
                "type": "string",
                "required": False,
                "description": "Investment type (LUMP_SUM or SIP)",
            },
            "org_id": {
                "type": "string",
                "required": False,
                "description": "Organization ID",
            },
            "active": {
                "type": "boolean",
                "required": False,
                "description": "Use active funds",
                "default": False,
            },
        },
    },
    "get_risk_profile": {
        "description": (
            "Returns the user's current overall risk profile (VERY_LOW, LOW, MEDIUM, HIGH, "
            "VERY_HIGH) by looking up their saved profile data. For newer onboarding users, "
            "portfolio style is retrieved directly. For older users, risk is inferred from "
            "age, income, and stated risk appetite. Returns overall_risk_profile plus "
            "component fields (age_range, income_range, risk_appetite — null for v2 users). "
            "Note: get_portfolio_options auto-fetches the user's risk profile internally, "
            "so you do NOT need to call get_risk_profile first when building a portfolio."
        ),
        "endpoint": "/cr/model-portfolio/get_risk_profile",
        "method": "POST",
        "parameters": {
            "user_id": {
                "type": "integer",
                "required": True,
                "description": "User ID to fetch risk profile for",
            },
        },
    },
    "risk_profile_v2": {
        "description": (
            "Calculates a detailed risk score based on personal and financial inputs. "
            "Used during onboarding or profile updates — NOT for checking an existing "
            "user's risk profile (use get_risk_profile for that). Blends financial risk "
            "capacity (80% weight) with stated willingness to lose (20% weight). "
            "Returns portfolio style recommendation (e.g. GROWTH, CONSERVATIVE) and "
            "allocation guidance. Result is saved to DB and used automatically by "
            "get_portfolio_options."
        ),
        "endpoint": "/cr/model-portfolio/risk_profile_v2",
        "method": "POST",
        "parameters": {
            "age": {
                "type": "integer",
                "required": True,
                "description": "Age (16-100)",
            },
            "pretax_income": {
                "type": "integer",
                "required": True,
                "description": "Annual pre-tax income in INR",
            },
            "pin_code": {
                "type": "integer",
                "required": True,
                "description": "PIN code for urban/rural classification",
            },
            "time_horizon": {
                "type": "string",
                "required": True,
                "description": "Investment time horizon",
                "enum": ["until_retirement", "short_term", "medium_term", "long_term"],
            },
            "willingness_to_lose_percentage": {
                "type": "number",
                "required": True,
                "description": "Willingness to lose percentage (0-100)",
            },
            "household_size": {
                "type": "integer",
                "required": False,
                "description": "Number of people in household",
                "default": 1,
            },
            "num_dependents": {
                "type": "integer",
                "required": False,
                "description": "Number of dependents",
                "default": 0,
            },
            "retirement_age": {
                "type": "integer",
                "required": False,
                "description": "Expected retirement age (30-100)",
                "default": 60,
            },
            "pay_consistency": {
                "type": "string",
                "required": False,
                "description": "Income stability",
                "enum": ["stable", "average", "uncertain"],
                "default": "average",
            },
            "income_sector_description": {
                "type": "string",
                "required": False,
                "description": "Text description of household occupations (max 500 chars)",
            },
            "healthy": {
                "type": "boolean",
                "required": False,
                "description": "Whether the user is healthy",
                "default": True,
            },
        },
    },
    "single_goal_optimizer": {
        "description": (
            "Pure financial calculator — given how much someone can invest and for how long, "
            "what are the chances of reaching a financial goal? Runs probability simulations "
            "across portfolio types to find the one that maximizes success. No user_id required. "
            "Returns success probability, optimal portfolio style, suggested equity %, and "
            "expected/best/worst wealth projections. "
            "Use this when the user has a specific goal with a target amount and timeline."
        ),
        "endpoint": "/cr/model-portfolio/single_goal_optimizer",
        "method": "POST",
        "parameters": {
            "investment_type": {
                "type": "string",
                "required": True,
                "description": "SIP (monthly) or LUMPSUM (one-time)",
                "enum": ["SIP", "LUMPSUM"],
            },
            "amount": {
                "type": "number",
                "required": True,
                "description": "Investment amount (monthly SIP or one-time lumpsum)",
            },
            "target_amount": {
                "type": "number",
                "required": True,
                "description": "Target corpus to achieve",
            },
            "time_horizon_months": {
                "type": "integer",
                "required": True,
                "description": "Number of months to achieve the goal",
            },
            "annual_step_up_rate": {
                "type": "number",
                "required": False,
                "description": "Annual SIP step-up rate (e.g., 0.10 for 10%). Only for SIP.",
                "default": 0.0,
            },
            "goal_type": {
                "type": "string",
                "required": False,
                "description": "Goal type",
                "enum": [
                    "RETIREMENT",
                    "HOUSE_PURCHASE",
                    "EMERGENCY_FUND",
                    "CHILD_EDUCATION",
                    "VACATION",
                    "WEALTH_CREATION",
                    "CAR_PURCHASE",
                    "CUSTOM",
                ],
                "default": "WEALTH_CREATION",
            },
            "risk_level": {
                "type": "string",
                "required": False,
                "description": (
                    "Risk level override. When provided, uses this portfolio category "
                    "instead of optimizing."
                ),
                "enum": [
                    "CAPITAL_PRESERVATION",
                    "DEFENSIVE",
                    "CONSERVATIVE",
                    "CONSERVATIVE_PLUS",
                    "BALANCED",
                    "BALANCED_PLUS",
                    "MODERATE",
                    "MODERATE_PLUS",
                    "GROWTH",
                    "GROWTH_PLUS",
                    "FOCUSED_GROWTH",
                ],
            },
            "show_funds": {
                "type": "boolean",
                "required": False,
                "description": "If true, include fund options in response",
                "default": False,
            },
            "loan_financing_amount": {
                "type": "number",
                "required": False,
                "description": "Amount covered by loan — subtracted from target amount",
            },
        },
    },
    "multi_goal_optimizer": {
        "description": (
            "Splits a fixed corpus and monthly SIP across multiple financial goals to "
            "maximize combined success. CRITICAL goals get 3x weight over ASPIRATIONAL. "
            "Supports 1-10 goals. No user_id required. "
            "Returns per-goal allocation (corpus %, SIP %), optimal portfolio per goal, "
            "and individual success probabilities. "
            "Use this when the user has multiple goals competing for the same money — "
            "for a single goal, use single_goal_optimizer instead."
        ),
        "endpoint": "/cr/model-portfolio/multi_goal_optimizer",
        "method": "POST",
        "parameters": {
            "total_corpus": {
                "type": "number",
                "required": True,
                "description": "Total initial corpus available for all goals",
            },
            "total_sip": {
                "type": "number",
                "required": True,
                "description": "Total monthly SIP available for all goals",
            },
            "goals": {
                "type": "array",
                "required": True,
                "description": (
                    "List of goals (1-10). Each goal: {goal_type, target_amount, "
                    "time_horizon_months, tier ('CRITICAL'|'IMPORTANT'|'ASPIRATIONAL'), "
                    "initial_corpus (optional), monthly_sip (optional)}"
                ),
            },
            "maxiter": {
                "type": "integer",
                "required": False,
                "description": "Max optimization iterations",
                "default": 500,
            },
        },
    },
    "goal_defaults": {
        "description": (
            "Given a goal target and time horizon, returns sensible default SIP and lumpsum "
            "amounts that would give roughly 70-75% chance of success. Used to pre-fill "
            "investment sliders so users have a realistic starting point. "
            "Returns default/min/max/step for both SIP and lumpsum, plus the portfolio "
            "assumptions (CAGR, volatility) used in the calculation."
        ),
        "endpoint": "/cr/model-portfolio/goal_defaults",
        "method": "POST",
        "parameters": {
            "target_amount": {
                "type": "number",
                "required": True,
                "description": "Goal target amount in INR",
            },
            "time_horizon_months": {
                "type": "integer",
                "required": True,
                "description": "Time horizon in months",
            },
            "goal_type": {
                "type": "string",
                "required": False,
                "description": "Type of goal",
                "default": "WEALTH_CREATION",
            },
            "loan_financing_amount": {
                "type": "number",
                "required": False,
                "description": "Amount covered by loan — subtracted from target before calculating defaults",
            },
        },
    },
    "build_stock_portfolio": {
        "description": (
            "Builds an optimized stock portfolio from a natural language query. Parses what "
            "the user wants (e.g. 'large cap tech stocks'), filters the stock universe to "
            "matching sectors/market caps, then selects and weights stocks to maximize "
            "Sharpe ratio. Returns stock allocations with weights, sector/market cap "
            "breakdown, and portfolio metrics."
        ),
        "endpoint": "/cr/model-portfolio/build_stock_portfolio",
        "method": "POST",
        "parameters": {
            "query": {
                "type": "string",
                "required": True,
                "description": (
                    "Natural language description of the desired portfolio, "
                    "e.g. 'Build me a large cap tech portfolio'"
                ),
            },
            "sectors": {
                "type": "array",
                "required": False,
                "description": "Optional sector filter override (bypasses NL parsing)",
            },
            "market_caps": {
                "type": "array",
                "required": False,
                "description": "Optional market cap filter (e.g. ['Large Cap', 'Mid Cap'])",
            },
            "max_stocks": {
                "type": "integer",
                "required": False,
                "description": "Maximum stocks in portfolio (2-20)",
                "default": 10,
            },
        },
    },
    "stock_to_fund": {
        "description": (
            "Looks at the user's existing direct stock holdings and recommends equivalent "
            "mutual funds with similar market exposure. Helps users transition from "
            "concentrated stock positions to diversified fund exposure while maintaining "
            "similar sector alignment. Returns fund recommendations matched to the user's "
            "current stock sectors and market cap categories."
        ),
        "endpoint": "/cr/model-portfolio/stock_to_fund",
        "method": "POST",
        "parameters": {
            "user_id": {
                "type": "integer",
                "required": True,
                "description": "User ID whose stock holdings to analyze",
            },
        },
    },
    "determine_income_sector": {
        "description": (
            "Classify household income sector from a text description of occupations. "
            "Uses LLM to map descriptions to standard income sector categories."
        ),
        "endpoint": "/cr/model-portfolio/determine_income_sector",
        "method": "POST",
        "parameters": {
            "description": {
                "type": "string",
                "required": True,
                "description": "Text description of occupation or work (max 500 chars)",
            },
        },
    },
    # =========================================================================
    # Financial Engine Service (/cr/fin-engine)
    # =========================================================================
    "financial_engine": {
        "description": (
            "Analyses a user's existing portfolio. All functions are accessed via this single "
            "endpoint using the function parameter. Available functions:\n"
            "- diversification: measures portfolio concentration using top-5 and top-20 holding percentages\n"
            "- sector_breakdown: portfolio exposure per market sector, plus overweight/underweight vs Nifty 500\n"
            "- asset_breakdown: split across equity, debt, cash, others\n"
            "- market_cap_breakdown: split across Large Cap, Mid Cap, Small Cap, others\n"
            "- single_holding_exposure: total exposure to a specific stock (direct + indirect via funds, 2 levels deep). Requires holding_name in parameters\n"
            "- total_stock_exposure: top-N stocks by exposure with per-fund contribution breakdown. Accepts optional top_n (int, default 5)\n"
            "- amc_preference: which AMCs the user is most concentrated in by value and fund count\n"
            "- sector_preference: overweight/underweight sectors vs Nifty 500 benchmark\n"
            "- theme_preference: thematic investment preferences (NOTE: currently placeholder — returns hardcoded data)\n"
            "- factor_preference: style factor scores (Momentum, Value, Low Volatility, Quality) on 0-100 scale\n"
            "Each function requires user_id (string) in the parameters dict. "
            "single_holding_exposure also requires holding_name (string)."
        ),
        "endpoint": "/cr/fin-engine/financial_engine",
        "method": "POST",
        "parameters": {
            "function": {
                "type": "string",
                "required": True,
                "description": "Analytics function to execute",
                "enum": [
                    "diversification",
                    "sector_breakdown",
                    "asset_breakdown",
                    "market_cap_breakdown",
                    "single_holding_exposure",
                    "total_stock_exposure",
                    "amc_preference",
                    "sector_preference",
                    "theme_preference",
                    "factor_preference",
                ],
            },
            "parameters": {
                "type": "object",
                "required": True,
                "description": (
                    "Function-specific parameters dict. Common fields: user_id (str), "
                    "org_id (int), external_user_id (str). Some functions need additional "
                    "fields: holding_name (str) for single_holding_exposure; "
                    "top_n (int, default 5) for total_stock_exposure."
                ),
            },
        },
    },
    # =========================================================================
    # ML Recommendations Service (/cr/mlr)
    # =========================================================================
    "ml_fund_discovery": {
        "description": (
            "Get personalized fund recommendations using collaborative filtering (ML-based). "
            "Finds funds similar to what users with similar portfolios hold. "
            "Different from search_funds — this uses the user's existing portfolio to find "
            "funds that similar investors hold, rather than searching by criteria."
        ),
        "endpoint": "/cr/mlr/fund_discovery",
        "method": "POST",
        "parameters": {
            "user_id": {
                "type": "integer",
                "required": True,
                "description": "User ID to generate recommendations for",
            },
        },
    },
}


def get_tools_prompt() -> str:
    """Render the TOOLS registry into a formatted string for the LLM system prompt."""
    lines = []
    for tool_name, tool_def in TOOLS.items():
        lines.append(f"### {tool_name}")
        lines.append(f"Description: {tool_def['description']}")
        lines.append("Parameters:")
        for param_name, param_def in tool_def["parameters"].items():
            req = "REQUIRED" if param_def.get("required") else "optional"
            ptype = param_def["type"]
            desc = param_def.get("description", "")
            default = param_def.get("default")
            enum = param_def.get("enum")

            parts = [f"  - {param_name} ({ptype}, {req}): {desc}"]
            if enum:
                parts.append(f"    Allowed values: {enum}")
            if default is not None:
                parts.append(f"    Default: {default}")
            lines.append("\n".join(parts))
        lines.append("")
    return "\n".join(lines)


def get_openai_tools() -> list[dict]:
    """Convert the TOOLS registry into OpenAI function-calling format.

    Returns a list of tool dicts ready to pass as the ``tools`` parameter
    to ``client.chat.completions.create()``.
    """
    openai_tools = []
    for tool_name, tool_def in TOOLS.items():
        properties = {}
        required = []
        for param_name, param_schema in tool_def["parameters"].items():
            prop: dict = {
                "type": param_schema["type"],
                "description": param_schema.get("description", ""),
            }
            if "enum" in param_schema:
                prop["enum"] = param_schema["enum"]
            if "default" in param_schema:
                prop["default"] = param_schema["default"]
            # OpenAI uses "object" for nested dicts and "array" for lists;
            # keep the type as-is since the backend expects these shapes.
            properties[param_name] = prop

            if param_schema.get("required"):
                required.append(param_name)

        openai_tools.append({
            "type": "function",
            "function": {
                "name": tool_name,
                "description": tool_def["description"],
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                },
            },
        })
    return openai_tools
