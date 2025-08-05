poetry build
cd dist
pip uninstall stallar_rpc
pip install stallar_rpc-0.1.0-py3-none-any.whl
cd ..
