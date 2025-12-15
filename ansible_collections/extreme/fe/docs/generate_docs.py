import os
import ast
import re

MODULES_DIR = '../plugins/modules'
DOCS_DIR = '.'

def extract_doc_string(filepath):
    with open(filepath, 'r') as f:
        content = f.read()
        # Simple regex extraction as ast might fail on some ansible constructs if not careful
        match = re.search(r'DOCUMENTATION\s*=\s*r?"""(.*?)"""', content, re.DOTALL)
        if match:
            return match.group(1)
        match = re.search(r"DOCUMENTATION\s*=\s*r?'''(.*?)'''", content, re.DOTALL)
        if match:
            return match.group(1)
    return None

def main():
    if not os.path.exists(DOCS_DIR):
        os.makedirs(DOCS_DIR)
    
    for filename in os.listdir(MODULES_DIR):
        if filename.endswith('.py') and filename != '__init__.py':
            filepath = os.path.join(MODULES_DIR, filename)
            doc = extract_doc_string(filepath)
            if doc:
                md_filename = filename.replace('.py', '.md')
                with open(os.path.join(DOCS_DIR, md_filename), 'w') as f:
                    f.write("# " + filename.replace('.py', '') + "\n\n")
                    f.write("```yaml\n" + doc + "\n```")
                    print(f"Generated {md_filename}")

if __name__ == '__main__':
    main()
