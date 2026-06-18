"""
Monkey-patch for magika to bypass onnxruntime DLL issues on Windows.
Provides a simple file extension-based content type detector.
"""
import os

# Content type map by extension
EXTENSION_MAP = {
    '.pdf': 'application/pdf',
    '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    '.doc': 'application/msword',
    '.pptx': 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
    '.ppt': 'application/vnd.ms-powerpoint',
    '.xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    '.xls': 'application/vnd.ms-excel',
    '.csv': 'text/csv',
    '.json': 'application/json',
    '.xml': 'application/xml',
    '.html': 'text/html',
    '.htm': 'text/html',
    '.md': 'text/markdown',
    '.txt': 'text/plain',
    '.png': 'image/png',
    '.jpg': 'image/jpeg',
    '.jpeg': 'image/jpeg',
    '.gif': 'image/gif',
    '.webp': 'image/webp',
    '.svg': 'image/svg+xml',
    '.mp3': 'audio/mpeg',
    '.wav': 'audio/wav',
    '.ogg': 'audio/ogg',
    '.m4a': 'audio/mp4',
    '.mp4': 'video/mp4',
    '.zip': 'application/zip',
    '.epub': 'application/epub+zip',
    '.py': 'text/x-python',
    '.yaml': 'text/yaml',
    '.yml': 'text/yaml',
    '.toml': 'text/toml',
}

class SimpleFileClassifier:
    """Drop-in replacement for magika that uses file extension detection."""
    
    @staticmethod
    def identify(file_path):
        ext = os.path.splitext(str(file_path))[1].lower()
        ct = EXTENSION_MAP.get(ext, 'application/octet-stream')
        return SimpleResult(ct)
    
    @staticmethod
    def identify_bytes(content):
        return SimpleResult('application/octet-stream')

class SimpleResult:
    def __init__(self, content_type):
        self.content_type = content_type
        self.magic = content_type
        self.status = "ok"
        self.prediction = type('obj', (object,), {
            'output': type('obj', (object,), {
                'content_type': content_type,
                'group': content_type.split('/')[0],
                'label': content_type.split('/')[-1] if '/' in content_type else content_type,
                'is_text': content_type.startswith('text/') or content_type in ('application/json', 'application/xml')
            }),
            'score': 0.95
        })


# Monkey-patch: Replace magika module before anything imports onnxruntime
import sys

class MockMagika:
    """Mock magika module that doesn't need onnxruntime."""
    
    class Magika:
        def __init__(self, *args, **kwargs):
            pass
        
        def identify(self, path):
            return SimpleFileClassifier.identify(path)
        
        def identify_bytes(self, content):
            return SimpleFileClassifier.identify_bytes(content)
        
        def identify_stream(self, stream):
            """Identify content type from a file stream."""
            import os
            if hasattr(stream, 'name'):
                ext = os.path.splitext(str(stream.name))[1].lower()
                ct = EXTENSION_MAP.get(ext, 'application/octet-stream')
            else:
                ct = 'application/octet-stream'
            return SimpleResult(ct)

# Create the mock module
mock_magika = type(sys)('magika')
mock_magika.Magika = MockMagika.Magika
mock_magika.__dict__['__builtins__'] = __builtins__

# Also provide a path for 'from magika import magika' pattern
class MagikaModule:
    Magika = MockMagika.Magika

sys.modules['magika'] = mock_magika
sys.modules['magika.magika'] = MockMagika  # Handle `from magika import magika`
sys.modules['magika.types'] = type(sys)('types')  # Basic types stub
sys.modules['magika.types'].ContentType = SimpleResult

print("[Patch] magika onnxruntime bypass installed successfully")
