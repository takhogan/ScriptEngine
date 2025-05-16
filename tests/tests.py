import json
import os
import tempfile
import zipfile
from pathlib import Path

def test_create_script_json_files():
    # Create a temporary directory for our test files
    with tempfile.TemporaryDirectory() as temp_dir:
        # Create the actions directory
        actions_dir = Path(temp_dir) / 'actions'
        actions_dir.mkdir()
        
        # Create sample JSON data
        action_rows = {
            "rows": [
                {"id": 1, "name": "Action 1"},
                {"id": 2, "name": "Action 2"}
            ]
        }
        
        props = {
            "property1": "value1",
            "property2": "value2"
        }
        
        inputs = {
            "input1": {"type": "string", "required": True},
            "input2": {"type": "number", "required": False}
        }
        
        outputs = {
            "output1": {"type": "string"},
            "output2": {"type": "number"}
        }
        
        # Write JSON files
        with open(actions_dir / 'actionRows.json', 'w') as f:
            json.dump(action_rows, f, indent=2)
            
        with open(Path(temp_dir) / 'props.json', 'w') as f:
            json.dump(props, f, indent=2)
            
        with open(Path(temp_dir) / 'inputs.json', 'w') as f:
            json.dump(inputs, f, indent=2)
            
        with open(Path(temp_dir) / 'outputs.json', 'w') as f:
            json.dump(outputs, f, indent=2)
            
        # Create a zip file containing all the JSON files
        zip_path = Path(temp_dir) / 'script.zip'
        with zipfile.ZipFile(zip_path, 'w') as script_zip:
            # Add all files to the zip
            for file_path in Path(temp_dir).rglob('*.json'):
                arcname = file_path.relative_to(temp_dir)
                script_zip.write(file_path, arcname)
                
        # Verify the files exist in the zip
        with zipfile.ZipFile(zip_path, 'r') as script_zip:
            assert 'actions/actionRows.json' in script_zip.namelist()
            assert 'props.json' in script_zip.namelist()
            assert 'inputs.json' in script_zip.namelist()
            assert 'outputs.json' in script_zip.namelist()
            
            # Verify the contents of one file as an example
            with script_zip.open('actions/actionRows.json', 'r') as f:
                loaded_action_rows = json.load(f)
                assert loaded_action_rows == action_rows
