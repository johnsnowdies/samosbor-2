"""
Tests for database models — structure, relationships, consistency.
Run: docker compose exec bot pytest tests/ -v
"""

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from bot.models import (
    Base,
    User,
    GameSession,
    Person,
    Player,
    NPC,
    Floor,
    Location,
    LocationConnection,
    Item,
    Task,
    SocialRelation,
    InteractionHistory,
    LocationVisitHistory,
    Conversation,
    DocumentChunk,
)


# ── Model Metadata Tests ──────────────────────────────

@pytest.mark.parametrize("model_cls,expected_table", [
    (User, "users"),
    (GameSession, "game_sessions"),
    (Person, "persons"),
    (Player, "players"),
    (NPC, "npcs"),
    (Floor, "floors"),
    (Location, "locations"),
    (LocationConnection, "location_connections"),
    (Item, "items"),
    (Task, "tasks"),
    (SocialRelation, "social_relations"),
    (InteractionHistory, "interaction_history"),
    (LocationVisitHistory, "location_visit_history"),
    (Conversation, "conversations"),
    (DocumentChunk, "document_chunks"),
])
def test_table_names(model_cls, expected_table):
    """All models have correct table names."""
    assert model_cls.__tablename__ == expected_table


@pytest.mark.parametrize("model_cls,expected_pk", [
    (User, ["id"]),
    (GameSession, ["id"]),
    (Person, ["id"]),
    (Player, ["person_id"]),
    (NPC, ["person_id"]),
    (Floor, ["id"]),
    (Location, ["id"]),
    (LocationConnection, ["from_location_id", "to_location_id"]),
    (Item, ["id"]),
    (Task, ["id"]),
    (SocialRelation, ["id"]),
    (InteractionHistory, ["id"]),
    (LocationVisitHistory, ["id"]),
    (Conversation, ["id"]),
    (DocumentChunk, ["id"]),
])
def test_primary_keys(model_cls, expected_pk):
    """All models have correct primary keys."""
    mapper = inspect(model_cls)
    pk_cols = [c.name for c in mapper.primary_key]
    assert pk_cols == expected_pk, f"{model_cls.__name__}: expected {expected_pk}, got {pk_cols}"


def test_all_models_have_session_id():
    """All session-scoped models have session_id FK."""
    session_scoped = [
        GameSession, Person, Player, NPC, Floor, Location,
        LocationConnection, Item, Task, SocialRelation,
        InteractionHistory, LocationVisitHistory, Conversation,
    ]
    for model in session_scoped:
        mapper = inspect(model)
        cols = {c.name for c in mapper.columns}
        # Session itself doesn't have session_id, it IS the session
        if model is GameSession:
            continue
        assert "session_id" in cols, f"{model.__name__} is missing session_id"
        col = mapper.columns["session_id"]
        assert col.foreign_keys, f"{model.__name__}.session_id has no FK"

    # DocumentChunk is global (not session-scoped)
    doc_mapper = inspect(DocumentChunk)
    assert "session_id" not in {c.name for c in doc_mapper.columns}


# ── Relationship Tests ────────────────────────────────

def test_user_game_session_relationship():
    """User → GameSession: one-to-many."""
    user = User(telegram_chat_id=12345)
    session1 = GameSession(user=user)
    session2 = GameSession(user=user)

    assert session1 in user.game_sessions
    assert session2 in user.game_sessions
    assert session1.user == user


def test_game_session_player_relationship():
    """GameSession → Player: one-to-one."""
    session = GameSession()
    player = Player(session=session)

    assert session.player == player
    assert player.session == session


def test_game_session_npc_relationship():
    """GameSession → NPC: one-to-many."""
    session = GameSession()
    npc1 = NPC(session=session)
    npc2 = NPC(session=session)

    assert npc1 in session.npcs
    assert npc2 in session.npcs


def test_person_current_location():
    """Person → Location: many-to-one."""
    location = Location(name="test")
    person = Person(name="Test", current_location=location)
    assert person.current_location == location


def test_person_inventory():
    """Person → Item: one-to-many via owner_id."""
    person = Person(name="Test")
    item1 = Item(name="Item1", owner=person)
    item2 = Item(name="Item2", owner=person)
    assert item1 in person.inventory
    assert item2 in person.inventory


def test_location_items():
    """Location → Item: one-to-many via location_id."""
    location = Location(name="Room")
    item = Item(name="Key", location=location)
    assert item in location.items


def test_location_connections():
    """Location → Location via LocationConnection (M2M)."""
    loc_a = Location(name="Room A")
    loc_b = Location(name="Room B")
    conn = LocationConnection(
        from_location=loc_a,
        to_location=loc_b,
        description="Door",
        transition_type="door",
    )
    assert conn in loc_a.connections_from
    assert conn in loc_b.connections_to


def test_social_relation():
    """SocialRelation links two persons with affinity."""
    person_a = Person(name="Alice")
    person_b = Person(name="Bob")
    rel = SocialRelation(from_person=person_a, to_person=person_b, affinity=0.5)
    assert rel in person_a.outgoing_relations
    assert rel.from_person == person_a
    assert rel.to_person == person_b


def test_task_assignee():
    """Task → Person: many-to-one."""
    person = Person(name="Test")
    task = Task(title="Find water", assignee=person)
    assert task in person.tasks
    assert task.assignee == person


def test_floor_location_relationship():
    """Floor → Location: one-to-many."""
    floor = Floor(name="Floor 1")
    loc = Location(name="Room", floor=floor)
    assert loc in floor.locations
    assert loc.floor == floor


def test_conversation_session_relationship():
    """Conversation → GameSession."""
    session = GameSession()
    conv = Conversation(session=session, role="user", content="Hello")
    assert conv in session.conversations


def test_interaction_history_relationships():
    """InteractionHistory → person + target_person."""
    alice = Person(name="Alice")
    bob = Person(name="Bob")
    interaction = InteractionHistory(
        person=alice,
        target_person=bob,
        event="Поговорили",
        cycle=1,
        time="08:00",
    )
    assert interaction.person == alice
    assert interaction.target_person == bob
    assert interaction in alice.interactions


def test_location_visit_history_relationships():
    """LocationVisitHistory → person + location."""
    person = Person(name="Wanderer")
    location = Location(name="Corridor")
    visit = LocationVisitHistory(
        person=person,
        location=location,
        visit_reason="Проходил мимо",
        cycle=1,
        time="12:00",
    )
    assert visit.person == person
    assert visit.location == location
    assert visit in person.location_visits


def test_npc_person_bidirectional():
    """NPC ↔ Person: bidirectional access."""
    person = Person(name="Bandit Leader")
    npc = NPC(person=person, faction="Ликвидаторы", danger_level=0.9)
    assert npc.person == person
    assert person.npc == npc
    assert person.npc.faction == "Ликвидаторы"
    assert npc.person.name == "Bandit Leader"


def test_player_person_bidirectional():
    """Player ↔ Person: bidirectional access."""
    person = Person(name="Hero")
    player = Player(person=person)
    assert player.person == person
    assert person.player == player
    assert person.player.person.name == "Hero"


def test_session_owns_all_entities():
    """GameSession has all collections: npcs, floors, locations, items, tasks, conversations."""
    session = GameSession()

    npc = NPC(session=session)
    floor = Floor(session=session, name="Test Floor")
    location = Location(session=session, name="Test Room", floor=floor)
    item = Item(session=session, name="Test Item")
    task = Task(session=session, title="Test Task", assignee=Person(name="Dummy"))
    conv = Conversation(session=session, role="user", content="Hi")
    rel = SocialRelation(session=session, from_person=Person(name="A"), to_person=Person(name="B"), affinity=0.0)
    interaction = InteractionHistory(session=session, person=Person(name="A"), target_person=Person(name="B"), event="x", cycle=1, time="08:00")
    visit = LocationVisitHistory(session=session, person=Person(name="A"), location=location, cycle=1, time="08:00")

    assert npc in session.npcs
    assert floor in session.floors
    assert location in session.locations
    assert item in session.items
    assert task in session.tasks
    assert conv in session.conversations
    assert rel in session.social_relations
    assert interaction in session.interactions
    assert visit in session.location_visits


def test_location_connection_bidirectional():
    """LocationConnection: from_location ↔ to_location."""
    loc_a = Location(name="Room A")
    loc_b = Location(name="Room B")
    conn = LocationConnection(
        from_location=loc_a,
        to_location=loc_b,
        description="Дверь",
        transition_type="door",
        is_locked=True,
    )
    assert conn.from_location == loc_a
    assert conn.to_location == loc_b
    assert conn in loc_a.connections_from
    assert conn in loc_b.connections_to
    assert conn.is_locked is True


def test_item_owner_and_location_are_optional():
    """Item can have owner_id=None and location_id=None simultaneously."""
    item = Item(name="Loose Item", item_type="misc")
    assert item.owner_id is None
    assert item.location_id is None
    assert item.is_equipped is False


def test_item_belongs_to_session():
    """Item → GameSession."""
    session = GameSession()
    item = Item(session=session, name="Key")
    assert item.session == session
    assert item in session.items


def test_task_defaults():
    """Task defaults: is_completed=False, location_id=None, reward=None, summary=None."""
    task = Task(title="Find water", assignee=Person(name="Someone"))
    assert task.is_completed is False
    assert task.location_id is None
    assert task.reward is None
    assert task.summary is None
    assert task.location_hint is None


def test_social_relation_affinity_range():
    """SocialRelation affinity supports full range -1.0..1.0."""
    p1 = Person(name="A")
    p2 = Person(name="B")
    hate = SocialRelation(from_person=p1, to_person=p2, affinity=-1.0)
    love = SocialRelation(from_person=p1, to_person=p2, affinity=1.0)
    neutral = SocialRelation(from_person=p1, to_person=p2, affinity=0.0)
    decimal = SocialRelation(from_person=p1, to_person=p2, affinity=-0.333)
    assert hate.affinity == -1.0
    assert love.affinity == 1.0
    assert neutral.affinity == 0.0
    assert decimal.affinity == -0.333


def test_floor_defaults():
    """Floor defaults: is_inhabited=True, danger_level=0.0, is_contaminated=False."""
    floor = Floor(name="Default Floor")
    assert floor.is_inhabited is True
    assert floor.danger_level == 0.0
    assert floor.is_contaminated is False


def test_npc_defaults():
    """NPC defaults: danger_level=0.0, faction=None."""
    npc = NPC(person=Person(name="Mystery"))
    assert npc.danger_level == 0.0
    assert npc.faction is None


def test_user_defaults():
    """User defaults: balance=0, trial_messages_left=5, is_admin=False, is_allowed=True."""
    user = User(telegram_chat_id=12345)
    assert user.balance == 0
    assert user.trial_messages_left == 5
    assert user.is_admin is False
    assert user.is_allowed is True


def test_game_session_defaults():
    """GameSession defaults: game_over=False, current_cycle=1, current_time='08:00'."""
    session = GameSession()
    assert session.game_over is False
    assert session.current_cycle == 1
    assert session.current_time == "08:00"


def test_item_type_default():
    """Item.item_type defaults to 'misc'."""
    item = Item(name="Something")
    assert item.item_type == "misc"


def test_location_connection_transition_type_default():
    """LocationConnection.transition_type defaults to 'door'."""
    conn = LocationConnection(
        from_location=Location(name="A"),
        to_location=Location(name="B"),
    )
    assert conn.transition_type == "door"


def test_document_chunk_creation():
    """DocumentChunk can be created with minimal fields."""
    from pgvector.sqlalchemy import Vector
    chunk = DocumentChunk(
        source="test_lore.txt",
        chunk_index=0,
        content="Sample text",
        embedding=Vector([0.0] * 1536),
    )
    assert chunk.source == "test_lore.txt"
    assert chunk.chunk_index == 0
    assert chunk.content == "Sample text"
    # Vector object stores the list internally, compare element count indirectly
    assert chunk.embedding is not None
    assert chunk.extra_meta == {}


def test_document_chunk_extra_meta_default():
    """DocumentChunk.extra_meta defaults to empty dict."""
    from pgvector.sqlalchemy import Vector
    chunk = DocumentChunk(
        source="test.md",
        chunk_index=1,
        content="More text",
        embedding=Vector([0.1] * 1536),
    )
    assert chunk.extra_meta == {}


def test_conversation_defaults():
    """Conversation defaults: cycle=1, tokens_used=0."""
    conv = Conversation(role="user", content="Hello")
    assert conv.cycle == 1
    assert conv.tokens_used == 0


def test_person_defaults():
    """Person defaults: bio='', personality='', appearance='', habits='', current_location_id=None."""
    person = Person(name="Nameless")
    assert person.bio == ""
    assert person.personality == ""
    assert person.appearance == ""
    assert person.habits == ""
    assert person.current_location_id is None


def test_location_defaults():
    """Location defaults: description=''."""
    location = Location(name="Empty Room")
    assert location.description == ""


def test_task_default_location_hint():
    """Task.location_hint defaults to None."""
    task = Task(title="Quest", assignee=Person(name="Hero"))
    assert task.location_hint is None


# ── __repr__ Tests ─────────────────────────────────

def test_person_repr():
    p = Person(id=1, name="Test")
    assert repr(p) == "<Person(id=1, name='Test')>"


def test_user_repr():
    u = User(id=1, telegram_chat_id=12345)
    assert repr(u) == "<User(id=1, chat_id=12345)>"


def test_game_session_repr():
    gs = GameSession(id=1, user_id=1)
    assert repr(gs) == "<GameSession(id=1, user=1, game_over=False)>"


def test_npc_repr():
    person = Person(name="Bandit")
    npc = NPC(person=person, faction="Бандиты")
    assert "Bandit" in repr(npc)
    assert "Бандиты" in repr(npc)


def test_location_repr():
    loc = Location(id=5, name="Комната 312")
    assert repr(loc) == "<Location(id=5, name='Комната 312')>"


def test_item_repr():
    item = Item(id=3, name="Нож")
    assert repr(item) == "<Item(id=3, name='Нож')>"


def test_task_repr():
    task = Task(id=2, title="Выжить")
    assert repr(task) == "<Task(id=2, title='Выжить')>"


def test_social_relation_repr():
    rel = SocialRelation(from_person_id=1, to_person_id=2, affinity=0.5)
    assert "1 → 2" in repr(rel)
    assert "0.5" in repr(rel)


def test_floor_repr():
    floor = Floor(id=1, name="Этаж 345")
    assert repr(floor) == "<Floor(id=1, name='Этаж 345')>"


def test_location_connection_repr():
    conn = LocationConnection(from_location_id=1, to_location_id=2)
    assert "1 → 2" in repr(conn)


def test_conversation_repr():
    conv = Conversation(id=1, role="user")
    assert repr(conv) == "<Conversation(id=1, role='user')>"


def test_document_chunk_repr():
    chunk = DocumentChunk(id=1, source="lore.txt", chunk_index=3)
    assert "lore.txt" in repr(chunk)
    assert "chunk=3" in repr(chunk)


# ── Inheritance Tests ─────────────────────────────────

def test_player_inherits_person():
    """Player has a Person via person_id FK."""
    person = Person(name="Player1")
    player = Player(person=person)
    assert player.person == person
    assert person.player == player
    assert person.name == "Player1"


def test_npc_inherits_person():
    """NPC has a Person via person_id FK."""
    person = Person(name="Bandit")
    npc = NPC(person=person, faction="Ликвидатор", danger_level=0.8)
    assert npc.person == person
    assert person.npc == npc
    assert npc.faction == "Ликвидатор"


def test_player_has_person_fields():
    """Player fields include inherited Person fields."""
    person = Person(name="Hero", bio="A brave hero")
    player = Player(person=person)
    assert player.person.name == "Hero"
    assert player.person.bio == "A brave hero"


# ── DB Integration Tests ─────────────────────────────


@pytest.mark.db
@pytest.mark.parametrize("chat_id", [10001, 10002, 999999999])
def test_create_multiple_users(db_session: Session, chat_id: int):
    """Create multiple users with different chat_ids."""
    user = User(telegram_chat_id=chat_id)
    db_session.add(user)
    db_session.commit()
    saved = db_session.query(User).filter_by(telegram_chat_id=chat_id).first()
    assert saved is not None
    assert saved.telegram_chat_id == chat_id


@pytest.mark.db
def test_user_game_session_cascade_delete(db_session: Session):
    """Deleting User cascades to GameSession and all child entities."""
    user = User(telegram_chat_id=20001)
    db_session.add(user)
    db_session.commit()

    session = GameSession(user=user, current_cycle=10, current_time="12:00")
    db_session.add(session)
    db_session.commit()

    # Add children
    person = Person(session=session, name="Victim")
    db_session.add(person)
    db_session.commit()

    db_session.add_all([
        Player(person=person, session=session),
        NPC(person=person, session=session, faction="Test"),
    ])
    floor = Floor(session=session, name="Floor 1")
    db_session.add(floor)
    db_session.commit()

    location = Location(session=session, name="Room", floor=floor)
    db_session.add(location)
    db_session.commit()

    item = Item(session=session, name="Item", owner=person)
    task = Task(session=session, title="Task", assignee=person)
    conv = Conversation(session=session, role="user", content="msg")
    db_session.add_all([item, task, conv])
    db_session.commit()

    # Delete user → cascade everything
    db_session.delete(user)
    db_session.commit()

    assert db_session.query(GameSession).count() == 0
    assert db_session.query(Person).count() == 0
    assert db_session.query(Player).count() == 0
    assert db_session.query(NPC).count() == 0
    assert db_session.query(Floor).count() == 0
    assert db_session.query(Location).count() == 0
    assert db_session.query(Item).count() == 0
    assert db_session.query(Task).count() == 0
    assert db_session.query(Conversation).count() == 0


@pytest.mark.db
def test_session_cascade_delete_person(db_session: Session):
    """Deleting GameSession cascades to Persons."""
    user = User(telegram_chat_id=20002)
    db_session.add(user)
    db_session.commit()

    session = GameSession(user=user)
    db_session.add(session)
    db_session.commit()

    p1 = Person(session=session, name="Alice")
    p2 = Person(session=session, name="Bob")
    db_session.add_all([p1, p2])
    db_session.commit()

    db_session.delete(session)
    db_session.commit()

    assert db_session.query(Person).count() == 0


@pytest.mark.db
def test_session_cascade_delete_locations(db_session: Session):
    """Deleting GameSession cascades to Floors and Locations."""
    user = User(telegram_chat_id=20003)
    db_session.add(user)
    db_session.commit()

    session = GameSession(user=user)
    db_session.add(session)
    db_session.commit()

    floor = Floor(session=session, name="Test Floor")
    db_session.add(floor)
    db_session.commit()

    loc1 = Location(session=session, name="Room A", floor=floor)
    loc2 = Location(session=session, name="Room B", floor=floor)
    db_session.add_all([loc1, loc2])
    db_session.commit()

    conn = LocationConnection(
        from_location=loc1, to_location=loc2, description="Door",
        session=session,
    )
    db_session.add(conn)
    db_session.commit()

    db_session.delete(session)
    db_session.commit()

    assert db_session.query(Floor).count() == 0
    assert db_session.query(Location).count() == 0
    assert db_session.query(LocationConnection).count() == 0


@pytest.mark.db
def test_session_cascade_delete_social_graph(db_session: Session):
    """Deleting GameSession cascades to SocialRelation and InteractionHistory."""
    user = User(telegram_chat_id=20004)
    db_session.add(user)
    db_session.commit()

    session = GameSession(user=user)
    db_session.add(session)
    db_session.commit()

    p1 = Person(session=session, name="Alice")
    p2 = Person(session=session, name="Bob")
    db_session.add_all([p1, p2])
    db_session.commit()

    rel = SocialRelation(session=session, from_person=p1, to_person=p2, affinity=0.5)
    hist = InteractionHistory(session=session, person=p1, target_person=p2, event="met", cycle=1, time="08:00")
    db_session.add_all([rel, hist])
    db_session.commit()

    db_session.delete(session)
    db_session.commit()

    assert db_session.query(SocialRelation).count() == 0
    assert db_session.query(InteractionHistory).count() == 0


@pytest.mark.db
def test_item_owner_set_null_on_person_delete(db_session: Session):
    """Deleting Person sets Item.owner_id to NULL (no cascade)."""
    user = User(telegram_chat_id=30001)
    db_session.add(user)
    db_session.commit()

    session = GameSession(user=user)
    db_session.add(session)
    db_session.commit()

    person = Person(session=session, name="Owner")
    db_session.add(person)
    db_session.commit()

    item = Item(session=session, name="Sword", owner=person, item_type="weapon")
    db_session.add(item)
    db_session.commit()
    assert item.owner_id == person.id

    db_session.delete(person)
    db_session.commit()

    # Item should still exist, but owner_id should be NULL
    saved_item = db_session.query(Item).filter_by(id=item.id).first()
    assert saved_item is not None
    assert saved_item.owner_id is None


@pytest.mark.db
def test_multiple_npcs_in_session(db_session: Session):
    """Session can have multiple NPCs with different factions."""
    user = User(telegram_chat_id=40001)
    db_session.add(user)
    db_session.commit()

    session = GameSession(user=user)
    db_session.add(session)
    db_session.commit()

    npcs_data = [
        ("Бандит", "Меченый", 0.9),
        ("Торговец", "Подпольщик", 0.1),
        ("Мутант", None, 0.5),
    ]
    for name, faction, danger in npcs_data:
        p = Person(session=session, name=name)
        db_session.add(p)
        db_session.commit()
        npc = NPC(person=p, session=session, faction=faction, danger_level=danger)
        db_session.add(npc)
        db_session.commit()

    assert db_session.query(NPC).count() == 3
    assert db_session.query(NPC).filter(NPC.faction == "Меченый").count() == 1
    assert db_session.query(NPC).filter(NPC.faction.is_(None)).count() == 1


@pytest.mark.db
def test_person_multiple_tasks(db_session: Session):
    """Person can have multiple tasks assigned."""
    user = User(telegram_chat_id=50001)
    db_session.add(user)
    db_session.commit()

    session = GameSession(user=user)
    db_session.add(session)
    db_session.commit()

    hero = Person(session=session, name="Hero")
    db_session.add(hero)
    db_session.commit()

    tasks = [
        Task(session=session, title="Найти воду", assignee=hero),
        Task(session=session, title="Починить фильтр", assignee=hero),
        Task(session=session, title="Выжить", assignee=hero, is_completed=True),
    ]
    db_session.add_all(tasks)
    db_session.commit()

    saved_hero = db_session.query(Person).filter_by(id=hero.id).first()
    assert len(saved_hero.tasks) == 3
    completed = [t for t in saved_hero.tasks if t.is_completed]
    assert len(completed) == 1
    assert completed[0].title == "Выжить"


@pytest.mark.db
def test_full_social_graph_traversal(db_session: Session):
    """Social graph: multiple persons with relations in both directions."""
    user = User(telegram_chat_id=60001)
    db_session.add(user)
    db_session.commit()

    session = GameSession(user=user)
    db_session.add(session)
    db_session.commit()

    names = ["Alice", "Bob", "Charlie", "Diana"]
    persons = []
    for name in names:
        p = Person(session=session, name=name)
        db_session.add(p)
        db_session.commit()
        persons.append(p)

    # Alice → Bob: 0.8, Alice → Charlie: -0.3
    # Bob → Alice: 0.5, Bob → Diana: 0.0
    # Charlie → Alice: -0.9, Charlie → Diana: 0.2
    relations = [
        SocialRelation(session=session, from_person=persons[0], to_person=persons[1], affinity=0.8),
        SocialRelation(session=session, from_person=persons[0], to_person=persons[2], affinity=-0.3),
        SocialRelation(session=session, from_person=persons[1], to_person=persons[0], affinity=0.5),
        SocialRelation(session=session, from_person=persons[1], to_person=persons[3], affinity=0.0),
        SocialRelation(session=session, from_person=persons[2], to_person=persons[0], affinity=-0.9),
        SocialRelation(session=session, from_person=persons[2], to_person=persons[3], affinity=0.2),
    ]
    db_session.add_all(relations)
    db_session.commit()

    # Verify from Alice's perspective
    alice = db_session.query(Person).filter_by(name="Alice").first()
    assert len(alice.outgoing_relations) == 2
    alice_relations = {r.to_person.name: r.affinity for r in alice.outgoing_relations}
    assert alice_relations["Bob"] == 0.8
    assert alice_relations["Charlie"] == -0.3

    # Verify from Charlie's perspective
    charlie = db_session.query(Person).filter_by(name="Charlie").first()
    assert len(charlie.outgoing_relations) == 2

    # Verify total relations in session
    total = db_session.query(SocialRelation).filter(
        SocialRelation.session_id == session.id
    ).count()
    assert total == 6


@pytest.mark.db
def test_location_floor_relationship(db_session: Session):
    """Location → Floor: verified through DB persistence."""
    user = User(telegram_chat_id=70001)
    db_session.add(user)
    db_session.commit()

    session = GameSession(user=user)
    db_session.add(session)
    db_session.commit()

    floor = Floor(session=session, name="Этаж 345", danger_level=0.7, is_contaminated=True)
    db_session.add(floor)
    db_session.commit()

    loc = Location(session=session, name="Коридор", floor=floor, description="Тёмный коридор")
    db_session.add(loc)
    db_session.commit()

    saved_loc = db_session.query(Location).filter_by(id=loc.id).first()
    assert saved_loc.floor.name == "Этаж 345"
    assert saved_loc.floor.danger_level == 0.7
    assert saved_loc.floor.is_contaminated is True

    assert loc in floor.locations


@pytest.mark.db
def test_location_visit_history_persistence(db_session: Session):
    """LocationVisitHistory: person visits a location."""
    user = User(telegram_chat_id=80001)
    db_session.add(user)
    db_session.commit()

    session = GameSession(user=user)
    db_session.add(session)
    db_session.commit()

    floor = Floor(session=session, name="Floor 1")
    db_session.add(floor)
    db_session.commit()

    loc = Location(session=session, name="Canteen", floor=floor)
    db_session.add(loc)
    db_session.commit()

    person = Person(session=session, name="Visitor", current_location=loc)
    db_session.add(person)
    db_session.commit()

    visit = LocationVisitHistory(
        session=session,
        person=person,
        location=loc,
        visit_reason="Поиск еды",
        cycle=3,
        time="14:30",
    )
    db_session.add(visit)
    db_session.commit()

    saved_visit = db_session.query(LocationVisitHistory).filter_by(id=visit.id).first()
    assert saved_visit.person.name == "Visitor"
    assert saved_visit.location.name == "Canteen"
    assert saved_visit.visit_reason == "Поиск еды"
    assert saved_visit.cycle == 3
    assert saved_visit.time == "14:30"


@pytest.mark.db
def test_conversation_history_ordering(db_session: Session):
    """Conversations are stored and ordered by created_at."""
    from datetime import datetime, timezone

    user = User(telegram_chat_id=90001)
    db_session.add(user)
    db_session.commit()

    session = GameSession(user=user)
    db_session.add(session)
    db_session.commit()

    messages = [
        Conversation(session=session, role="user", content="Привет", cycle=1, tokens_used=10),
        Conversation(session=session, role="assistant", content="И добрый день", cycle=1, tokens_used=50),
        Conversation(session=session, role="user", content="Кто ты?", cycle=1, tokens_used=8),
        Conversation(session=session, role="assistant", content="Я NPC", cycle=2, tokens_used=30),
    ]
    db_session.add_all(messages)
    db_session.commit()

    saved = db_session.query(Conversation).filter(
        Conversation.session_id == session.id
    ).order_by(Conversation.id).all()
    assert len(saved) == 4
    assert saved[0].content == "Привет"
    assert saved[-1].content == "Я NPC"
    assert saved[-1].cycle == 2


@pytest.mark.db
def test_location_connection_is_locked_default(db_session: Session):
    """LocationConnection.is_locked defaults to False."""
    user = User(telegram_chat_id=10001)
    db_session.add(user)
    db_session.commit()

    session = GameSession(user=user)
    db_session.add(session)
    db_session.commit()

    floor = Floor(session=session, name="Floor")
    db_session.add(floor)
    db_session.commit()

    loc_a = Location(session=session, name="A", floor=floor)
    loc_b = Location(session=session, name="B", floor=floor)
    db_session.add_all([loc_a, loc_b])
    db_session.commit()

    conn = LocationConnection(
        from_location=loc_a,
        to_location=loc_b,
        description="Проход",
        session=session,
    )
    db_session.add(conn)
    db_session.commit()

    saved = db_session.query(LocationConnection).first()
    assert saved.is_locked is False
    assert saved.transition_type == "door"


@pytest.mark.db
def test_game_session_advance_time(db_session: Session):
    """GameSession current_cycle and current_time can be updated."""
    user = User(telegram_chat_id=11001)
    db_session.add(user)
    db_session.commit()

    session = GameSession(user=user, current_cycle=1, current_time="08:00")
    db_session.add(session)
    db_session.commit()

    # Advance time
    session.current_cycle = 2
    session.current_time = "12:30"
    db_session.commit()

    saved = db_session.query(GameSession).filter_by(id=session.id).first()
    assert saved.current_cycle == 2
    assert saved.current_time == "12:30"


@pytest.mark.db
def test_user_balance_update(db_session: Session):
    """User balance can be updated."""
    user = User(telegram_chat_id=12001, balance=10, trial_messages_left=5)
    db_session.add(user)
    db_session.commit()

    # Spend a message
    user.balance -= 1
    user.trial_messages_left -= 1
    db_session.commit()

    saved = db_session.query(User).filter_by(telegram_chat_id=12001).first()
    assert saved.balance == 9
    assert saved.trial_messages_left == 4

@pytest.mark.db
def test_create_user_in_db(db_session: Session):
    """Create User and persist."""
    user = User(telegram_chat_id=99999, balance=100, trial_messages_left=3)
    db_session.add(user)
    db_session.commit()

    saved = db_session.query(User).filter_by(telegram_chat_id=99999).first()
    assert saved is not None
    assert saved.balance == 100
    assert saved.trial_messages_left == 3
    assert saved.is_allowed is True
    assert saved.is_admin is False


@pytest.mark.db
def test_create_full_session(db_session: Session):
    """Create a complete game session with player, NPC, locations."""
    # 1. User
    user = User(telegram_chat_id=88888)
    db_session.add(user)
    db_session.commit()

    # 2. Session
    session = GameSession(user=user, current_cycle=42, current_time="14:30")
    db_session.add(session)
    db_session.commit()

    # 3. Floor
    floor = Floor(session=session, name="Этаж 345", danger_level=0.3)
    db_session.add(floor)
    db_session.commit()

    # 4. Locations with connection
    loc_a = Location(session=session, name="Коридор", floor=floor)
    loc_b = Location(session=session, name="Комната 312", floor=floor)
    db_session.add_all([loc_a, loc_b])
    db_session.commit()

    conn = LocationConnection(
        from_location=loc_a,
        to_location=loc_b,
        description="Дверь с номером 312",
        transition_type="door",
        session=session,
    )
    db_session.add(conn)
    db_session.commit()

    # 5. Player (person + player)
    player_person = Person(
        session=session,
        name="Игрок",
        bio="Житель Гигахрущёвки",
        current_location=loc_a,
    )
    db_session.add(player_person)
    db_session.commit()

    player = Player(person=player_person, session=session)
    db_session.add(player)
    db_session.commit()

    # 6. NPC
    npc_person = Person(
        session=session,
        name="Бандит",
        current_location=loc_a,
    )
    db_session.add(npc_person)
    db_session.commit()

    npc = NPC(person=npc_person, session=session, faction="Ликвидатор", danger_level=0.9)
    db_session.add(npc)
    db_session.commit()

    # 7. Items
    item = Item(session=session, name="Нож", owner=npc_person, item_type="weapon")
    db_session.add(item)
    db_session.commit()

    # 8. Task
    task = Task(session=session, title="Выжить", assignee=npc_person)
    db_session.add(task)
    db_session.commit()

    # 9. Social relation
    rel = SocialRelation(
        session=session,
        from_person=npc_person,
        to_person=player_person,
        affinity=-0.7,
    )
    db_session.add(rel)
    db_session.commit()

    # 10. Social relation FROM player TO npc
    rel2 = SocialRelation(
        session=session,
        from_person=player_person,
        to_person=npc_person,
        affinity=-0.5,
    )
    db_session.add(rel2)
    db_session.commit()

    # 11. Verify everything
    saved_session = db_session.query(GameSession).filter_by(id=session.id).first()
    assert saved_session is not None
    assert saved_session.current_cycle == 42
    assert saved_session.player.person.name == "Игрок"
    assert len(saved_session.npcs) == 1
    assert saved_session.npcs[0].person.name == "Бандит"
    assert len(saved_session.floors) == 1
    assert len(saved_session.locations) == 2

    # Verify social graph
    relations = db_session.query(SocialRelation).filter(
        SocialRelation.session_id == session.id
    ).all()
    assert len(relations) == 2

    # Verify task
    assert saved_session.tasks[0].title == "Выжить"

    # Verify item
    assert saved_session.items[0].name == "Нож"
    assert saved_session.items[0].owner.name == "Бандит"


@pytest.mark.db
def test_cascade_delete_user(db_session: Session):
    """Deleting User should cascade to GameSession."""
    user = User(telegram_chat_id=77777)
    db_session.add(user)
    db_session.commit()

    session = GameSession(user=user)
    db_session.add(session)
    db_session.commit()

    db_session.delete(user)
    db_session.commit()

    sessions = db_session.query(GameSession).filter_by(user_id=user.id).all()
    assert len(sessions) == 0


@pytest.mark.db
def test_telegram_chat_id_unique(db_session: Session):
    """telegram_chat_id must be unique."""
    user1 = User(telegram_chat_id=11111)
    db_session.add(user1)
    db_session.commit()

    user2 = User(telegram_chat_id=11111)
    db_session.add(user2)
    with pytest.raises(Exception):
        db_session.commit()
    db_session.rollback()


@pytest.mark.db
def test_person_current_location_fk(db_session: Session):
    """Person can have NULL current_location_id."""
    user = User(telegram_chat_id=13001)
    db_session.add(user)
    db_session.commit()

    session = GameSession(user=user)
    db_session.add(session)
    db_session.commit()

    person = Person(name="Loner", session=session)
    db_session.add(person)
    db_session.commit()

    saved = db_session.query(Person).filter_by(name="Loner").first()
    assert saved.current_location_id is None