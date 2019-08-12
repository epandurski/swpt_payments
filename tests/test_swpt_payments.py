from swpt_payments import __version__


def test_version(db_session):
    assert __version__
