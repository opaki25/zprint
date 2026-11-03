import io
import pytest
from pypdf import PdfReader, PdfWriter
from pypdf.generic import ArrayObject, DictionaryObject, NameObject, NumberObject, TextStringObject


def annotated_pdf(subtype='/Link', action='/URI', chained=False):
    writer = PdfWriter()
    writer.add_blank_page(595, 842)
    annotation = DictionaryObject({NameObject('/Type'): NameObject('/Annot'),
        NameObject('/Subtype'): NameObject(subtype),
        NameObject('/Rect'): ArrayObject([NumberObject(x) for x in (0, 0, 100, 20)])})
    if action:
        a = DictionaryObject({NameObject('/S'): NameObject(action)})
        if action == '/URI':
            a[NameObject('/URI')] = TextStringObject('https://example.com')
        if chained:
            a[NameObject('/Next')] = DictionaryObject({NameObject('/S'): NameObject('/JavaScript')})
        annotation[NameObject('/A')] = a
    writer.add_annotation(0, annotation)
    stream = io.BytesIO()
    writer.write(stream)
    return stream.getvalue()


@pytest.mark.parametrize('action', ['/URI', '/GoTo', None])
def test_ordinary_links_are_removed_before_preview(client, auth, action):
    response = client.post('/api/v1/documents', headers=auth, files={'file':('lecture.pdf', annotated_pdf(action=action),'application/pdf')})
    assert response.status_code == 201, response.text
    assert response.json()['page_count'] == 1
    assert 'links were removed' in response.json()['warnings'][0]
    preview = client.get(f'/api/v1/documents/{response.json()["id"]}/preview', headers=auth)
    reader = PdfReader(io.BytesIO(preview.content))
    assert '/Annots' not in reader.pages[0]
    assert '/A' not in reader.pages[0]


@pytest.mark.parametrize('subtype,action,chained', [('/Link','/JavaScript',False),('/Link','/Launch',False),('/Link','/URI',True),('/Text',None,False)])
def test_active_or_visible_annotations_remain_rejected(client, auth, subtype, action, chained):
    response = client.post('/api/v1/documents',headers=auth,files={'file':('lecture.pdf',annotated_pdf(subtype,action,chained),'application/pdf')})
    assert response.status_code == 422
    assert 'interactive' in response.json()['detail'] or 'annotations' in response.json()['detail']
    assert not list(client.app.state.settings.data_dir.glob('*.pdf'))
