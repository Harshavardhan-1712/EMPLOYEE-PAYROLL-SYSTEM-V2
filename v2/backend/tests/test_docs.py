from scripts import gen_docs


def test_generated_docs_are_up_to_date(capsys):
    """docs/api.md and docs/schema.md are generated from the code. If this fails: python -m scripts.gen_docs"""
    assert gen_docs.main(["--check"]) == 0, capsys.readouterr().out


def test_every_route_appears_in_the_api_doc():
    api = gen_docs.build_api()
    from app.main import ROUTERS
    from fastapi.routing import APIRoute
    for router in ROUTERS:
        for r in router.routes:
            if isinstance(r, APIRoute):
                for m in r.methods - {"HEAD", "OPTIONS"}:
                    assert f"| `{m}` | `/api{r.path}` |" in api


def test_every_table_and_trigger_appears_in_the_schema_doc():
    from app.models import Base
    from app.models.tables import _TRIGGERS
    sch = gen_docs.build_schema()
    for t in Base.metadata.sorted_tables:
        assert f"### `{t.name}`" in sch
    assert sch.count("trg_") >= len(_TRIGGERS)
