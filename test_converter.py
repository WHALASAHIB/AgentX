"""Test the new file converter."""
import sys
sys.path.insert(0, r'C:\Trading\backend')
from file_converter import convert_to_markdown

# Test with a text file
result = convert_to_markdown(r'C:\Trading\markitdown\README.md')
print('Filename:', result['filename'])
print('Type:', result['content_type'])
print('Size:', result['size'], 'bytes')
print('=== Content (first 500) ===')
print(result['text'][:500])
print('=== END ===')
