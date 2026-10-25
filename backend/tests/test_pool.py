from app.config import settings
from app.database import engine


def test_pool_de_conexoes_segue_a_configuracao():
    # cada instância da Function abre o próprio pool; o limite protege o PostgreSQL
    assert engine.pool.size() == settings.db_pool_size
    assert engine.pool._max_overflow == settings.db_max_overflow
    assert settings.db_pool_size + settings.db_max_overflow <= 10
