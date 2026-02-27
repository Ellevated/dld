#!/usr/bin/env bash
# setup-mcp.sh - Interactive MCP server setup for DLD
# Usage:
#   ./scripts/setup-mcp.sh          # Interactive tier selection
#   ./scripts/setup-mcp.sh --check  # Health check only
#   ./scripts/setup-mcp.sh --tier 2 # Non-interactive setup (1=Quick, 2=Standard, 3=Power)

set -euo pipefail

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# MCP Server definitions
CONTEXT7_CMD="claude mcp add context7 -- npx -y @context7/mcp-server"
EXA_CMD='claude mcp add --transport http exa "https://mcp.exa.ai/mcp?tools=web_search_exa,web_search_advanced_exa,get_code_context_exa,deep_search_exa,crawling_exa,company_research_exa,deep_researcher_start,deep_researcher_check"'

# Health check function
check_server() {
    local name=$1
    local test_cmd=$2

    printf "  Checking ${BLUE}%s${NC}... " "$name"

    if eval "$test_cmd" > /dev/null 2>&1; then
        echo -e "${GREEN}OK${NC}"
        return 0
    else
        echo -e "${RED}FAILED${NC}"
        return 1
    fi
}

# Health check all servers
health_check() {
    echo -e "\n${BLUE}MCP Health Check${NC}"
    echo "================="

    local all_ok=true

    # Check prerequisites
    echo -e "\n${YELLOW}Prerequisites:${NC}"
    check_server "Node.js" "node --version" || all_ok=false
    check_server "npx" "npx --version" || all_ok=false
    check_server "claude CLI" "command -v claude" || all_ok=false

    # Check MCP servers
    echo -e "\n${YELLOW}MCP Servers:${NC}"
    check_server "Context7" "npx -y @context7/mcp-server --help 2>&1 | head -1" || all_ok=false
    check_server "Exa (connectivity)" "curl -s --max-time 5 'https://mcp.exa.ai/mcp' | head -c 1" || all_ok=false

    echo ""
    if $all_ok; then
        echo -e "${GREEN}All checks passed!${NC}"
        return 0
    else
        echo -e "${RED}Some checks failed. See docs/21-mcp-troubleshooting.md${NC}"
        return 1
    fi
}

# Add server with health check
add_server() {
    local name=$1
    local cmd=$2
    local test_cmd=$3

    echo -e "\nAdding ${BLUE}$name${NC}..."

    if eval "$cmd" 2>&1; then
        if check_server "$name" "$test_cmd"; then
            return 0
        fi
    fi

    echo -e "${YELLOW}Warning: $name may not be working correctly${NC}"
    return 1
}

# Setup tier
setup_tier() {
    local tier=$1

    case $tier in
        1)
            echo -e "\n${GREEN}Quick: No MCP${NC}"
            echo "No MCP servers to configure. DLD will use built-in tools."
            ;;
        2)
            echo -e "\n${GREEN}Standard: Context7 + Exa${NC}"
            add_server "Context7" "$CONTEXT7_CMD" "npx -y @context7/mcp-server --help 2>&1 | head -1"
            add_server "Exa" "$EXA_CMD" "curl -s --max-time 5 'https://mcp.exa.ai/mcp' | head -c 1"
            ;;
        3)
            echo -e "\n${GREEN}Power: All MCP Servers${NC}"
            # First add Standard tier servers
            setup_tier 2

            echo -e "\n${YELLOW}Note: Memory MCP requires an API key.${NC}"
            echo "Get your key from Anthropic and add manually:"
            echo '  claude mcp add memory -- npx -y @anthropic/memory-mcp'
            echo ""
            echo "Sequential Thinking (no key needed):"
            echo '  claude mcp add sequential-thinking -- npx -y @anthropic/sequential-thinking-mcp'
            ;;
        *)
            echo -e "${RED}Invalid tier: $tier${NC}"
            exit 1
            ;;
    esac
}

# Interactive menu
interactive_menu() {
    echo -e "${BLUE}"
    echo "  ____  _     ____    __  __  ____ ____   ____       _"
    echo " |  _ \| |   |  _ \  |  \/  |/ ___|  _ \ / ___|  ___| |_ _   _ _ __"
    echo " | | | | |   | | | | | |\/| | |   | |_) | \___ \/ _ \ __| | | | '_ \\"
    echo " | |_| | |___| |_| | | |  | | |___|  __/  ___) |  __/ |_| |_| | |_) |"
    echo " |____/|_____|____/  |_|  |_|\____|_|    |____/ \___|\__|\__,_| .__/"
    echo "                                                              |_|"
    echo -e "${NC}"

    echo "Select MCP tier:"
    echo ""
    echo "  1) Quick      - No MCP (quick evaluation)"
    echo "  2) Standard   - Context7 + Exa (no API keys) [recommended]"
    echo "  3) Power      - + Memory + Sequential (requires keys)"
    echo "  4) Skip       - Exit without changes"
    echo ""

    read -rp "Your choice [2]: " choice
    choice=${choice:-2}

    case $choice in
        1|2|3)
            setup_tier "$choice"
            ;;
        4)
            echo "Skipped. Run again when ready."
            exit 0
            ;;
        *)
            echo -e "${RED}Invalid choice${NC}"
            exit 1
            ;;
    esac

    echo ""
    echo -e "${GREEN}Setup complete!${NC}"
    echo ""
    echo "Next steps:"
    echo "  1. Restart Claude Code to load MCP servers"
    echo "  2. Run: ./scripts/setup-mcp.sh --check"
    echo "  3. Try: /scout 'research topic'"
}

# Main
main() {
    case "${1:-}" in
        --check)
            health_check
            ;;
        --tier)
            if [[ -z "${2:-}" ]]; then
                echo "Usage: $0 --tier <1|2|3>"
                exit 1
            fi
            setup_tier "$2"
            ;;
        --help|-h)
            echo "Usage: $0 [--check | --tier <1|2|3>]"
            echo ""
            echo "Options:"
            echo "  --check       Run health check only"
            echo "  --tier N      Non-interactive setup (1=Quick, 2=Standard, 3=Power)"
            echo "  (no args)     Interactive menu"
            exit 0
            ;;
        *)
            interactive_menu
            ;;
    esac
}

main "$@"
