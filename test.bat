set cov=
set pythonpath=".\tests;.\stallar_rpc"
python -m pytest -v %cov% --html=report.html .\tests
