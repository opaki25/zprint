from types import SimpleNamespace
import pytest
from zprint.domain import transition, select_pages
from zprint.config import Settings


def test_unpaid_job_cannot_jump_to_printing():
    job = SimpleNamespace(status='AWAITING_PAYMENT')
    with pytest.raises(ValueError):
        transition(job, 'PRINTING')


def test_page_selection_normalizes_duplicates():
    assert select_pages('3,1-2,2', 4) == [1, 2, 3]


def test_production_fails_closed(tmp_path):
    with pytest.raises(RuntimeError, match='DEMO'):
        Settings(demo=False, data_dir=tmp_path).validate()
