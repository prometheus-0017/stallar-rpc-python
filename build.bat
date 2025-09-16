del /q dist\* 
poetry build
python -m twine upload dist/*
pip uninstall xuri_rpc
pip install xuri_rpc -i https://pypi.org/simple/
