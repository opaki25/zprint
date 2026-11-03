from pathlib import Path
from pypdf import PdfWriter

output = Path('data/sample-15-pages.pdf')
output.parent.mkdir(parents=True, exist_ok=True)
writer = PdfWriter()
for _ in range(15):
    writer.add_blank_page(595.28, 841.89)
with output.open('wb') as stream:
    writer.write(stream)
print(f'Created deterministic 15-page blank A4 test document: {output.resolve()}')
