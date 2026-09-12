from alcana_bot.lang_store import LangStore

def test_get_language_defaults_when_unset(tmp_path):
    store = LangStore(str(tmp_path / "user_lang.json"))
    assert store.get_language(12345) == "uz"

def test_set_then_get_language_roundtrip(tmp_path):
    store = LangStore(str(tmp_path / "user_lang.json"))
    store.set_language(12345, "ru")
    assert store.get_language(12345) == "ru"

def test_language_persists_across_new_instance(tmp_path):
    file_path = str(tmp_path / "user_lang.json")
    store1 = LangStore(file_path)
    store1.set_language(999, "ru")

    store2 = LangStore(file_path)
    assert store2.get_language(999) == "ru"
