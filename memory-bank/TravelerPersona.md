## Overview
For information about Roamly, please first see the RoamlyOverview.md

### Problem Statement
For Roamly, we need a way to build a very high-level understanding of our user. We need a way to learn their preferences, interests, and tastes not linked to a specific trip or tour. Just learning their personality and who they are as a person without anything attached. 

### Solution
We will create a high-level Traveler Persona for each traveler once they register for our application. This persona will be dynamically updated over time. 


### Problem Statement
When a traveler is on a trip, we want a way to learn and manage their preferences specific to that trip. Often times, users prefer different things trip to trip. For example, if it is summer, they want to go to the beach and do more adventurous activities. If it is the holidays, they may want to take it easy and spend more time with family. We need something that builds off the higher level Traveler Persona (and does not contradict it), but adds more specificity just at the trip level. 

### Solution
We can create a **Trip Level Persona** for each trip. We will store all the trips user is part of in the **Traveler Persona**, and for each of the trips, link to this **Trip Level Persona**. This will include more specific information regarding the trip, and will help us in building trip-level itineraries for the user and recommending things for multi-day events. 

Some additional things we would maybe store at this level would be:

- **Calendar integration:** See free blocks of time, infer constraints.
- **Travel booking imports:** Flights, trains, hotels (with user permission).
- **Maps/ride-share integration:** Real-time context (traffic, rideshare cost).
- **Social data (later stage):** Interests from Spotify, TikTok, or Instagram activity (with explicit consent).
- **Weather & local feeds:** Contextual enrichment, as you already noted.

(non-exhaustive list, will be changed as design/development continues)

### Problem Statement
When a traveler is on a trip, and in some city, and wants to launch a guided tour or learn about the different events, foods, or transportation near their location, we need a way to keep track of their specific preferences at that moment while integrating the information stored at the Trip Level Persona and Traveler Persona. 

### Solution
We can create a **Tour-Guide Level Persona** for each trip. We will store all the tours that user is part of in the **Trip-Level Persona**, and for each of the tour guides, link to this **Trip Level Persona**. This will include gathering more specific information from the user, taking into consideration location, time of day, weather, mood, etc, and many other lower-level factors to curate and recommend a tour for a user.

We will also support 3 main modes for the user they can launch from wherever they are:

- [DRIVE MODE TOGGLE] User has a vehicle
- [WALK MODE TOGGLE] User is walking
- [HYBRID MODE TOGGLE/DEFAULT TOGGLE] User makes use of both

### Information We Will Store

- **Location context**: current GPS, nearby events, safety alerts.
- **Time window**: available hours today, hard deadlines.
- **Budget per outing**: per-tour spend (separate from whole trip budget).
- **Transport mode**: walking, car, rideshare, public transit.
- **Current companions**: solo, with kids, with friends.
- **Energy/mood check**: quick toggle (relaxed, balanced, adventurous, party).
- **Meal preferences right now**: hungry? want sit-down or quick bite?
- **Dynamic state**:
    - Skipped stops.
    - Stayed too long → re-route.
    - “Like/dislike” feedback during tour.

### How to capture:

- **Quick-start toggles**: “How much time do you have?” “What’s your energy level?”
- **Context-driven defaults**: time of day → suggest meals, evening → nightlife.
- **Passive signals**: walking pace from GPS, location linger times, group size from shared app accounts.

---

## Core Parameters

### Location Context

- Safety warnings (government feeds)
- Local events (festivals, live music, shows, ticket/cost info)
- Transportation updates (rideshare surge, bus availability, taxi wait times)

**User Stories:**

- *As a traveler, I want the app to warn me if protests or strikes make an area unsafe.*
- *As a music lover, I want to see nearby live events I can add to my tour.*
- *As a budget traveler, I want to know if taxis are cheaper than Uber today.*

---

### Time

- Tour duration (1h, 3h, half-day, full-day)
- Buffer for meals / train / airport schedules
- Dynamic re-routing if time spent differs from plan
- Walking speed/fitness calibration from Traveler Persona

**User Stories:**

- *As a traveler, I want to choose a 1-hour walking tour that matches my fitness so I don’t miss my train.*
- *As a time-crunched traveler, I want only tours that fit into my 3-hour window before my meeting.*
- *As a traveler who likes to move fast, I want a “speedy” version that skips long waits.*
- *As a traveler who hates to rush, I want extra buffer time so I can relax without stress.*

---

### Budget

- Per-tour budget input
- Paid/free filter for activities
- Cost breakdown: transport, entry fees, food
- ATMs/cash stops flagged along route
- Future: trip-level budget optimization

**User Stories:**

- *As a traveler, I want to set a €50 limit for my Rome tour so I don’t overspend.*
- *As a foodie, I don’t care about total budget as long as I eat authentic local food quickly before my train.*
- *As a tight-budget traveler, I want only free activities recommended.*
- *As a budget-conscious traveler, I want to see cost breakdowns before committing.*

---

### Residence / Hotel

- Starting point
- Preferred endpoint (return to hotel, train station, nightlife area, etc.)

**User Stories:**

- *As a traveler, I want my tour to start at my hotel and end at the train station before departure.*
- *As a nightlife traveler, I want my tour to finish near bars instead of my hotel.*

---

### Transport & Tickets

- Mode: walking, car, public transport
- Integration with pre-purchased tickets (train, bus, Uber passes, museums)

**User Stories:**

- *As a traveler, I want to upload my train ticket so the app ensures I end near the station in time.*
- *As a driver, I want parking suggestions included in my vehicle tour.*

---

### Past Tours

- Adjust intensity based on last activity
- Learn preferences (liked/disliked, skipped stops)

**User Stories:**

- *As a traveler who did an intense hike yesterday, I want today’s suggestions to be more relaxed.*
- *As a traveler who disliked the last museum, I want different options this time.*

---

### Companions & Group Type

- Solo, family, couple, friends
- Kids, seniors, accessibility (wheelchair/stroller)
- Group size

**User Stories:**

- *As a parent with kids, I want tours that include playgrounds and bathrooms.*
- *As a couple, I want romantic evening walking tours with fewer crowds.*

---

### Mood & Energy

- Relaxed / Balanced / Adventure / Party toggle

**User Stories:**

- *As a party traveler, I want my day tour to end in a nightlife district.*
- *As a relaxed traveler, I want a low-effort scenic walk instead of rushing through sites.*

---

### Food & Drink

- Cuisine preferences (local, fine dining, street food)
- Dietary restrictions (vegan, halal, allergies)
- Alcohol preferences

**User Stories:**

- *As a foodie, I want authentic but non-touristy food stops included.*
- *As a vegan, I want the app to only suggest plant-based restaurants.*

---

### Sustainability

- Eco-friendly mode (bike, walk, public transport)
- Local business preference

**User Stories:**

- *As an eco-conscious traveler, I want tours that avoid taxis when possible.*
- *As a local-supporting traveler, I want small shops and family restaurants prioritized.*

---

### Safety & Comfort

- Night vs. day tours
- Safety ratings of neighborhoods
- Alerts for protests, closures

**User Stories:**

- *As a solo female traveler, I want evening tours in lively, safe areas.*
- *As a cautious traveler, I want warnings if an area is currently restricted or unsafe.*

---

### Tech/Connectivity

- Offline maps/audio
- Battery-saving routing

**User Stories:**

- *As a traveler without mobile data, I want downloadable offline tours.*
- *As a traveler with low phone battery, I want routes that minimize GPS use.*

## 2. Traveler Persona

See [Traveler Persona](https://www.notion.so/Traveler-Persona-2500319c82cd80e7abf5cbb968eb6965?pvs=21) 

### Health & Fitness

- Walking speed, stamina, accessibility needs
- Sleep/energy levels

**User Stories:**

- *As a traveler with limited stamina, I want short tours with rest stops.*
- *As a tired traveler, I want a chill, café-heavy tour instead of a long hike.*

---

## 3. Tour Flow & Flexibility

- Dynamic re-routing if user stays too long, skips a stop, or misses a train
- End-point preferences

**User Stories:**

- *As a traveler, I want my tour to automatically adjust if I linger longer at a café.*
- *As a business traveler, I want to always end near my next meeting location.*



TravelerPersona.JSON
```
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
```

TripPersonaJSON
```
{
  "trip_id": "Aug_2025_LosAngeles",
  "customerId": "user_id_from_your_auth_system",
  "location": {
    "city": "Los Angeles",
    "country": "United States"
  },
  "dates": {
    "start": "2025-08-01",
    "end": "2025-08-08"
  },
  "preferences": {
    "focus": "Culture & History",
    "pace": "Take it slow",
    "authenticity": "Local experiences"
  },
  "itinerary_link": "s3://customerid_username_bucket/trips/Aug_2025_LosAngeles_itinerary.json",

  "custom_tours": {
    "Aug5_SunsetBlvd_Night_Tour": {
      "tour_id": "Aug5_SunsetBlvd_Night_Tour",
      "tour_name": "Sunset Boulevard Night Tour",
      "createdAt": "2025-08-05T00:00:00Z",
      "tour_link": "s3://customerid_username_bucket/tours/Aug5_SunsetBlvd_Night_Tour.json"
    }
  }
}
```

CustomTourPersonaJSON
```
{
  "tour_id": "Aug5_SunsetBlvd_Night_Tour",
  "trip_id": "Aug_2025_LosAngeles",
  "tour_name": "Sunset Boulevard Night Tour",
  "date": "2025-08-05",
  "duration": "3 hours",
  "preferences": {
    "focus": "Nightlife",
    "pace": "Leisurely",
    "authenticity": "Local hotspots"
  },
  "notes": "Booked via Roamly AI Tour Creator v1.2"
}
```

Hierarchy Overview
S3 Bucket: customerid_username_bucket/
│
├── travelerPersona.json                     <-- Root persona (demographics + high-level prefs + trip links)
│
├── trips/
│   ├── Aug_2025_LosAngeles_trip.json        <-- Trip persona (trip-level preferences, itineraries, tours)
│   └── May_2026_Rome_trip.json
│
└── tours/
    ├── Aug5_SunsetBlvd_Night_Tour.json      <-- Tour-level personas
    └── Aug6_GriffithObservatoryTour.json



- `travelerPersona.json` — the root persona for the user (demographics, top-level preferences, and links to trips)
- `trips/` — folder containing per-trip JSONs (linked from the main persona)
- `tours/` — folder containing detailed tour-level JSONs (linked from individual trip JSONs)

If the S3 bucket already exists, return a successful message:
