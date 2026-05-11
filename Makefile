.PHONY: test demo backtest optimizer audit outputs compile help

help:
	@echo "LSEG Listed-Options Delta-Hedging & Delta-Vega Optimization Engine"
	@echo ""
	@echo "Targets (all use --mock / offline data unless LSEG/IBKR is available):"
	@echo "  make test       Run full test suite"
	@echo "  make compile    Syntax-check all src/ and scripts/"
	@echo "  make demo       Run offline Greeks + hedge demo"
	@echo "  make backtest   Run LSEG delta-only historical backtest (--mock)"
	@echo "  make optimizer  Run 4-method delta-vega optimizer (--mock)"
	@echo "  make audit      Run LSEG option universe audit (--mock)"
	@echo "  make outputs    Regenerate all charts and report CSVs"
	@echo "  make all        compile + test + demo + backtest + optimizer + audit"

compile:
	python -m compileall src scripts

test:
	pytest

demo:
	python scripts/run_demo.py

backtest:
	python scripts/run_lseg_historical_hedge_backtest.py --mock

optimizer:
	python scripts/run_delta_vega_hedge_optimizer.py --mock

audit:
	python scripts/audit_lseg_option_universe.py --mock

outputs:
	python scripts/build_readme_outputs.py

all: compile test demo backtest optimizer audit
