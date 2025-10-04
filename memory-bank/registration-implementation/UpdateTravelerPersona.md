## Background
I am still working on implementing the registration workflow. Now that we have the registration endpoint setup, I want to create and implement the /UpdateTravelerPersona function/endpoint that will take in data we get from when user performs registration workflow and creates the traveler persona JSON. 

## Tasks

Ideally, what will happen is that the registration endpoint will recieve some JSON with some fields/data that we will want to add to our Traveler Persona JSON files. Currently, the registration endpoint does not accept that since we are still determining what to pass in from frontend, but we can add maybe a placeholder and some empty JSON file as a defaily value for now. 

The flow would be that the /registration endpoint, before adding information to the database, would call a /updateTravelerPersona endpoint here in Roamly service. Maybe we can put it in its own python file. 



### Task 1: Implement `create_customer_bucket()` Function
This function will live in its own Python file called `s3_operations.py`. This python file will contain all the functions that we use to interact with AWS S3 for storig and retrieving customer information. 

**input**: customerId, username
**output**: Logs to console that bucket was created succesfully/unsuccesfully

if it does not exist already, creates an ***empty*** S3 bucket by the format of `customerid_username_bucket`. This will be used to store the following structure

customerid_username_bucket/
│
--- customerId_trip_year_itinerary.json
--- customerId_recommendations.json
├── travelerPersona.json
├── trips/
│ └── trip_id_trip.json
│
└── tours/
└── tour_id_tour.json

- `travelerPersona.json` — the root persona for the user (demographics, top-level preferences, and links to trips)
- `trips/` — folder containing per-trip JSONs (linked from the main persona)
- `tours/` — folder containing detailed tour-level JSONs (linked from individual trip JSONs)

If the S3 bucket already exists, return a successful message:


If the S3 bucket exists already, return with the succesfull message saying "customerid_username_bucket already exists"



---

### Task 2: Implement `/UpdateTravelerPersona` Endpoint

This endpoint will be called at different stages in the app.  
Initially, it will be triggered by the `/register` endpoint when onboarding a new user.  
In the future, whenever we learn new information about the user (from activity, feedback, or preferences), other endpoints may also call this endpoint to update their Traveler Persona.

**Input:** `customerId`, `username`, and optional `updates` JSON  
**Output:** Creates or updates a hierarchical persona JSON structure in S3.

#### Flow:

1. Check if the S3 bucket for the user exists.
   - Call `create_customer_bucket(customerId, username)`.
   - If it returns "customerid_username_bucket already exists", continue using that bucket.
   - If it fails, log an error and stop registration.

2. Once the bucket exists, check for the main `travelerPersona.json`:
   - If it **does not exist**, create a new persona JSON (see below).

### Traveler Persona JSON Structure (Updated for Hybrid Model)

This is the new structure that reflects the **three-tiered hierarchy**:
1. Traveler Persona (root)
2. Trip Personas (stored separately in `/trips/`)
3. Custom Tour Personas (stored separately in `/tours/`)

```json
{
  "customerId": "user_id_from_your_auth_system",
  "version": "1.0",
  "lastUpdated": "2025-10-03T00:00:00Z",

  "demographics": {
    "firstName": "Alex",
    "lastName": "Jones",
    "DOB": "2003-08-04",
    "sex": "Male",
    "hometown": {
      "city": "Berlin",
      "country": "Germany"
    }
  },

  "travel_persona": {
    "travel_companions": ["Friends", "Solo"],
    "preferences": {
      "vibe": "Relaxing",
      "focus": "Culture & History",
      "pace": "Take it slow",
      "authenticity": "Local experiences",
      "social_style": "Group camaraderie"
    },
    "habits": {
      "spending": "Comfortable",
      "interests": [
        "Food & Drink",
        "Relaxation & Wellness",
        "Culture & History",
        "Ancient History",
        "Fine Dining"
      ]
    },
    "trips": {
      "Aug_2025_LosAngeles": {
        "trip_id": "Aug_2025_LosAngeles",
        "trip_name": "Los Angeles Summer Trip 2025",
        "createdAt": "2025-08-01T00:00:00Z",
        "updatedAt": "2025-08-05T00:00:00Z",
        "trip_link": "s3://customerid_username_bucket/trips/Aug_2025_LosAngeles_trip.json"
      },
      "May_2026_Rome": {
        "trip_id": "May_2026_Rome",
        "trip_name": "Rome Cultural Tour 2026",
        "createdAt": "2026-05-01T00:00:00Z",
        "updatedAt": "2026-05-04T00:00:00Z",
        "trip_link": "s3://customerid_username_bucket/trips/May_2026_Rome_trip.json"
      }
    }
  }
}


This wil be the general structure of a traveler persona for a user. It is a tiered persona at three levels. Highest level is the Traveler Persona, second level is the trip persona, and third level is the custom tour guide persona. For more information, see TravelerPersona.md. 


#### Traveler Persona JSON Already Exists

Whenever we have some new information about the user we want to store, we will come in this situation. The traveler persona already exists, but this /UpdateTravelerPersona endpoint is called again. We need to update specific areas/fields of the persona. 

To approach this, we can implement the following
```python
def deep_update(original: dict, updates: dict) -> dict:
    """
    Recursively merges updates into the original dict.
    - Nested dicts are updated in-place (not replaced).
    - Lists are appended to and deduplicated.
    - Scalar values are replaced.
    """
    for key, value in updates.items():
        if isinstance(value, dict) and isinstance(original.get(key), dict):
            # Merge nested dictionaries
            deep_update(original[key], value)
        elif isinstance(value, list) and isinstance(original.get(key), list):
            # Merge and deduplicate list items
            merged_list = original[key] + value
            # Preserve order while removing duplicates
            seen = set()
            original[key] = [x for x in merged_list if not (x in seen or seen.add(x))]
        else:
            # Overwrite or add new keys
            original[key] = value
    return original
```

Here is how it would look in action

Input: 
```json
existing = {
    "travel_persona": {
        "habits": {
            "interests": ["Food & Drink", "Culture & History"]
        }
    }
}

updates = {
    "travel_persona": {
        "habits": {
            "interests": ["Adventure Sports", "Culture & History"]
        }
    }
}
```

Output:
```json
    {
  "travel_persona": {
    "habits": {
      "interests": ["Food & Drink", "Culture & History", "Adventure Sports"]
    }
  }
}
```

So this deep update doesn't replace the entire object, it adds to it.


If we want to delete/remove a preference, instead of actually deleting or removing the item (in case user changes their mind or whatever, we can do this:)
{
  "travel_persona": {
    "habits": {
      "interests": {
        "__delete__": ["Culture & History"]
      }
    }
  }
}

And so then our processors would recognize this down the line and choose to not include certain things in recommendations/etc.
