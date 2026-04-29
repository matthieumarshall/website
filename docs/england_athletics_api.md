# Event Provider API

There are 6 available methods:

1. Returns an individual URN based on first name, last name, and date of birth.
2. Returns individual details based on URN.
3. Returns roles held by an individual based on URN.
4. Returns the full list of current clubs.
5. Returns all athletes within a given club.

## General

All calls must be HTTPS (HTTP will not be accepted).

All calls take 3 headers which allow us to identify the caller and ensure the request is valid from a security perspective. If the method call is to the Authenticate Methods, then you need to pass the user's password in the header to protect it.

The 3 mandatory headers are:

| Header | Description |
|---|---|
| `X-TRAPI-CALLKEY` | A string key (essentially a username) given to the API caller. |
| `X-TRAPI-CALLSECRET` | A string secret (essentially a password) given to the API caller. |
| `X-TRAPI-CALLDATETIME` | UTC datetime string at time of calling, format `yyyy-MM-ddTHH:mm:ss`. Example: `2018-01-15T13:28:25`. |

The password must be URL-encoded and passed in the `X-TRAPI-USERPASSWORD` header.

You'll need to attach a client certificate to the request. This is different for Staging and Live, so you'll need to be able to switch between the two. The certificate and password will be provided for each environment.

The timestamp is used to reduce the possibility of replay attacks — the time must be close to the server time.

Security checks are performed server-side. Failed requests are logged internally but only return either `ApiUserCredentialsIncorrect` or `InvalidCall`. Contact the team if you receive either of these errors and they will advise on the underlying cause.

Text passed in the URL must be URL-encoded, as some data (e.g. `&`) is not valid in URL parameters.

### Note for PHP/CURL Users

Add the following config to force HTTP/1.1, as HTTP/2 does not yet support client certificates:

```php
curl_setopt($ch, CURLOPT_HTTP_VERSION, CURL_HTTP_VERSION_1_1);
```

## Client Certificates

The system uses client certificates. Each API consumer is given a client certificate and password, which only they hold. The certificate must be loaded into the **Local Machine's Personal certificate store** on the machine originating the API calls. The API calls include the certificate, which is validated by the server.

The certificate and password are provided on request and shared securely.

## API Callers

Each caller will be granted (on supply of appropriate data sharing agreements and rules for use) a username, password, client certificate, and certificate password.

## How to Use the Event Provider API

The Event Provider API is based on the following workflow:

1. The event provider solution authenticates the person externally.
2. The API provides methods for authentication using the person's Trinity username and password, but this is **not** provided to Event Providers at this stage.
3. The provider uses the **Search Individual** method to compare the URN entered by the athlete against their entered first name, last name, and date of birth. This identifies the person if the information matches.
4. The API returns the person's registration status and their club.
5. The competition provider uses the date of birth returned by the API to calculate the athlete's competing age category.
6. **GetClubs** should be called infrequently (at most once per week) to get and cache the club list — the data changes very rarely.
7. If the individual wishes to enter other athletes from their club, the provider calls **Get Roles** to check whether the individual holds a role that permits them to enter a team for a club.

### Roles That Allow Entering Athletes for a Club

- Coach
- Chairperson
- Club Secretary
- Coaching Coordinator
- Membership Secretary
- President
- Running Group Leader
- Treasurer

If the individual holds one of these roles, they may view and enter other athletes from their club. The API returns the registration status for each club athlete, allowing the race provider to decide how to handle unregistered athletes.

In most cases the date of the event is passed to the API, which returns whether the person will be registered on that date.

**Live:** `https://TrinityAPI.myathletics.uk/TrinityAPIService.svc/`

**Staging:** `https://staging.myathletics.uk/TrinityAPIstaging/TrinityAPIService.svc/`

## Staging Test Credentials — STAGING LINK IS PENDING

| Field | Value |
|---|---|
| User | `eventprov2` |
| Password | `$33#(sport2` |
| Certificate | `TrApiStagingEVENT2ClientCert.pfx` |
| Certificate password | `EvSTg@561760v2` |

## Method Calls

### Search Individual (first / last / DOB)

Looks up an individual by name and date of birth and returns their URN if a unique match is found.

**URL format:**

```
SERVER/race-provider/individuals?firstname={providedFirstName}&lastname={providedLastName}&dob={providedDob}
```

**Response status options:** `InvalidCall`, `ApiUserCredentialsIncorrect`, `InternalError`, `NoMatch`, `MultipleMatches`, `MatchFound`

**Example**

Request:
```
GET https://TrinityAPI.myathletics.uk/TrinityAPIService.svc/race-provider/individuals?firstname=peter&lastname=bramley&dob=11+August+1970
```

Response:
```json
{
  "IndividualRef": 3693653,
  "ResponseReference": "f87f4997-f178-4681-8d79-7e766f7bceeb",
  "ResponseStatus": "MatchFound"
}
```

---

### Get Roles (URN)

Returns the club roles held by an individual, identified by URN.

**URL format:**

```
SERVER/race-provider/individuals/{providedUrn}/roles
```

**Response status options:** `InvalidCall`, `ApiUserCredentialsIncorrect`, `InternalError`, `UnknownUrn`, `SuccessfullyCompleted`

**Example 1 — no roles**

Request:
```
GET https://TrinityAPI.myathletics.uk/TrinityAPIService.svc/race-provider/individuals/3693653/roles
```

Response:
```json
{
  "ResponseStatus": "SuccessfullyCompleted",
  "ResponseReference": "c916900f-c1b3-40d8-8bbb-ad72d35780b1",
  "Roles": null
}
```

**Example 2 — with roles**

Request:
```
GET https://TrinityAPI.myathletics.uk/TrinityAPIService.svc/race-provider/individuals/3361037/roles
```

Response:
```json
{
  "ResponseStatus": "SuccessfullyCompleted",
  "ResponseReference": "4eb00427-f6d5-421f-8e0b-c893c483e944",
  "Roles": [
    {
      "CanEnterATeamforClub": "True",
      "Category": "Competitive",
      "ClubId": "1765",
      "ClubName": "zzz Runners",
      "RoleName": "Athlete"
    }
  ]
}
```

---

### Get Clubs

Returns the full list of current clubs. Call infrequently — at most once per week.

**URL format:**

```
SERVER/race-provider/clubs
```

**Response status options:** `InvalidCall`, `ApiUserCredentialsIncorrect`, `InternalError`, `SuccessfullyCompleted`

**Example**

Request:
```
GET https://TrinityAPI.myathletics.uk/TrinityAPIService.svc/race-provider/clubs
```

Response:
```json
{
  "Clubs": [
    {
      "ClubId": "1528",
      "ClubName": "100 Marathon Club",
      "HomeCountry": "EA",
      "Locality": "London",
      "Region": "London"
    }
  ]
}
```
