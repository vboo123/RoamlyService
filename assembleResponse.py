from cassandra.cluster import Cluster

# Connect to Cassandra
cluster = Cluster(['127.0.0.1'])
session = cluster.connect()
session.set_keyspace('roamly_keyspace')

def assemble_response(property_id: str, user_country: str = "default", interests: list[str] = None) -> str:
    semantic_keys = ["origin.general", "height.general", "media.references"]
    facts = {}

    for key in semantic_keys:
        rows = session.execute("""
            SELECT response, user_country FROM semantic_responses
            WHERE property_id = %s AND semantic_key = %s ALLOW FILTERING
        """, (property_id, key))

        selected = ""
        for row in rows:
            if row.user_country == user_country:
                selected = row.response.strip()
                break
            elif row.user_country == "default" and not selected:
                selected = row.response.strip()
        facts[key] = selected

    # Optionally tweak response using interests
    interest_phrase = ""
    if interests:
        if "Movies" in interests or "TV" in interests:
            interest_phrase = "If you're into films, you'll especially love this spot! "
        elif "Photography" in interests:
            interest_phrase = "It’s also a favorite for photographers. "
        elif "History" in interests:
            interest_phrase = "Its long history makes it a must-see. "
        # Add more personalized tweaks as desired

    template = (
        "Hey there! Welcome to the {landmark}. {origin} Fun fact: {height} "
        "{interest_phrase}Also, {media} Hope you're enjoying your trip!"
    )

    return template.format(
        landmark=property_id,
        origin=facts.get("origin.general", ""),
        height=facts.get("height.general", ""),
        media=facts.get("media.references", ""),
        interest_phrase=interest_phrase
    )
