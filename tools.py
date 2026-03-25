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
            "'SBI funds with high returns'. Returns ranked fund recommendations."
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
            "Finds funds ranked higher than the current holding based on returns, risk, or cost."
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
            "Build a model portfolio with fund options for a given investment amount, "
            "risk preference, and investment type. Returns fund options per segment, "
            "allocation percentages, default selections, backtest results, and metrics."
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
            "Run a backtest on a user-selected portfolio (after getting portfolio options). "
            "Validates selected funds match required segments and returns performance metrics."
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
                    "Selected funds per segment. Keys: equity, debt, alternatives, cash. "
                    "Values: dict mapping segment name to ISIN. "
                    'Example: {"equity": {"large_cap": "INF123..."}, "debt": {"gilt": "INF456..."}}'
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
            "Legacy portfolio construction endpoint. Builds a portfolio with dynamic fund "
            "selection and returns time series, metrics, and returns analysis."
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
            "Get a user's risk profile based on their stored attributes "
            "(age, income, risk appetite). Returns overall risk profile and component scores."
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
            "Enhanced risk profiling with detailed inputs. Calculates risk score based on "
            "age, income, time horizon, willingness to lose, household factors, and health. "
            "Returns portfolio style recommendation and allocation guidance."
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
            "Calculate investment needed for a single financial goal. Optimizes portfolio "
            "allocation to maximize success probability. Returns required SIP/lumpsum, "
            "wealth projections (expected/worst/best case), and portfolio recommendations."
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
        },
    },
    "multi_goal_optimizer": {
        "description": (
            "Optimize investment allocation across multiple competing financial goals. "
            "Uses differential evolution to maximize weighted success probability. "
            "Handles goal prioritization via tiers (CRITICAL, IMPORTANT, ASPIRATIONAL)."
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
            "Get default investment assumptions for goal planning. Returns recommended "
            "SIP and lumpsum defaults (min/max/step) based on goal parameters."
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
        },
    },
    "build_stock_portfolio": {
        "description": (
            "Build a portfolio from individual stocks. Calculates sector and market cap "
            "diversification, returns portfolio metrics and recommendations."
        ),
        "endpoint": "/cr/model-portfolio/build_stock_portfolio",
        "method": "POST",
        "parameters": {
            "stocks": {
                "type": "array",
                "required": True,
                "description": "List of stocks with weights: [{symbol, weight}, ...]",
            },
        },
    },
    "stock_to_fund": {
        "description": (
            "Convert stock holdings to mutual fund recommendations. Analyzes existing "
            "stock portfolio and suggests mutual funds to replace concentrated positions."
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
            "Run portfolio analytics functions. Supported functions: "
            "diversification, sector_breakdown, asset_breakdown, market_cap_breakdown, "
            "single_holding_exposure, total_stock_exposure, amc_preference, "
            "sector_preference, theme_preference, factor_preference. "
            "Each function takes a parameters dict with user_id, org_id, and function-specific args."
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
                    "fields like security_name for single_holding_exposure."
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
            "Finds funds similar to what users with similar portfolios hold."
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
