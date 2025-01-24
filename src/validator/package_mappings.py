"""Package name mappings for the import validator."""

# Known module-to-package mappings
MODULE_TO_PACKAGE = {
    'yaml': 'pyyaml',
    'PIL': 'pillow',
    'bs4': 'beautifulsoup4',
    'sklearn': 'scikit-learn',
    'cv2': 'opencv-python',
    'psycopg2': 'psycopg2-binary',
    'pydantic_settings': 'pydantic-settings'
}

# Reverse mapping for package-to-module
PACKAGE_TO_MODULES = {
    'pyyaml': ['yaml'],
    'pillow': ['PIL'],
    'beautifulsoup4': ['bs4'],
    'scikit-learn': ['sklearn'],
    'opencv-python': ['cv2'],
    'psycopg2-binary': ['psycopg2'],
    'pydantic-settings': ['pydantic_settings']
} 