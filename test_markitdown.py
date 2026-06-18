"""Test MarkItDown converters directly."""
import sys
sys.path.insert(0, r'C:\Trading\backend')

# Apply magika patch
import magika_patch

# Now import converter directly - bypass main MarkItDown class
from markitdown.converters.text_converter import TextConverter
from markitdown._stream_info import StreamInfo

file_path = r'C:\Trading\markitdown\README.md'
with open(file_path, 'rb') as f:
    content = f.read()

stream_info = StreamInfo(mimetype='text/markdown', extension='.md', local_path=file_path)

converter = TextConverter()
result = converter.convert(content, stream_info=stream_info)
print('=== MarkItDown Output ===')
print(result.text_content[:500])
print('=== END ===')
