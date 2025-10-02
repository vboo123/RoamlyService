# Roamly Service - Refactored

A simplified FastAPI service that provides user authentication functionality with DynamoDB integration.

## Features

- **User Registration**: Register new users with validation
- **User Login**: Authenticate users with JWT tokens
- **Rate Limiting**: Built-in rate limiting for security
- **DynamoDB Integration**: Uses AWS DynamoDB for user storage

## API Endpoints

### POST /register-user/
Register a new user.

**Request Body:**
```json
{
    "name": "John Doe",
    "email": "john@example.com",
    "country": "United States",
    "language": "English",
    "age": 25,
    "interestOne": "Technology"
}
```

**Response:**
```json
{
    "status": "success",
    "message": "User registered successfully",
    "user_id": "uuid-here",
    "user": { ... }
}
```

### GET /login/
Login with name and email.

**Query Parameters:**
- `name`: User's name
- `email`: User's email

**Response:**
```json
{
    "user": { ... },
    "token": "jwt-token-here"
}
```

### GET /docs
Interactive API documentation (Swagger UI)

## Setup

1. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Set environment variables:**
   ```bash
   export AWS_ACCESS_KEY_ID="your-access-key"
   export AWS_SECRET_ACCESS_KEY="your-secret-key"
   export JWT_SECRET="your-jwt-secret"
   ```

3. **Run the application:**
   ```bash
   python3 -m uvicorn app:app --reload --port 8000
   ```

4. **Test the application:**
   ```bash
   python3 test_app.py
   ```

## Environment Variables

- `AWS_ACCESS_KEY_ID`: AWS access key for DynamoDB
- `AWS_SECRET_ACCESS_KEY`: AWS secret key for DynamoDB
- `JWT_SECRET`: Secret key for JWT token generation (default: "supersecretkey")

## Database Schema

### Users Table
- `user_id` (String, Primary Key)
- `name` (String)
- `email` (String, Index)
- `country` (String)
- `language` (String)
- `age` (Number)
- `interestOne` (String)
- `created_at` (String, ISO format)
- `last_login` (String, ISO format)

## What Was Removed

This refactored version removes all landmark-related functionality:
- Semantic search services
- Audio processing
- Landmark endpoints
- S3 integration for configuration files
- All landmark-related dependencies

The codebase is now focused solely on user authentication and management.