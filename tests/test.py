import pytest

@pytest.mark.parametrize("x", [1, 2, 3])
def test_add(x):
    assert x + 1 == x + 1