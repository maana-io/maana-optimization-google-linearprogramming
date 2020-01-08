from __future__ import print_function
from ariadne import ObjectType, QueryType, MutationType, gql, make_executable_schema
from ariadne.asgi import GraphQL
from asgi_lifespan import Lifespan, LifespanMiddleware
from graphqlclient import GraphQLClient

# HTTP request library for access token call
import requests
# .env
from dotenv import load_dotenv
import os

# Google OR Tools

from ortools.linear_solver import pywraplp
    
# Load environment variables
load_dotenv()


def getAuthToken():
    authProvider = os.getenv('AUTH_PROVIDER')
    authDomain = os.getenv('AUTH_DOMAIN')
    authClientId = os.getenv('AUTH_CLIENT_ID')
    authSecret = os.getenv('AUTH_SECRET')
    authIdentifier = os.getenv('AUTH_IDENTIFIER')

    # Short-circuit for 'no-auth' scenario.
    if(authProvider == ''):
        print('Auth provider not set. Aborting token request...')
        return None

    url = ''
    if authProvider == 'keycloak':
        url = f'{authDomain}/auth/realms/{authIdentifier}/protocol/openid-connect/token'
    else:
        url = f'https://{authDomain}/oauth/token'

    payload = {
        'grant_type': 'client_credentials',
        'client_id': authClientId,
        'client_secret': authSecret,
        'audience': authIdentifier
    }

    headers = {'content-type': 'application/x-www-form-urlencoded'}

    r = requests.post(url, data=payload, headers=headers)
    response_data = r.json()
    print("Finished auth token request...")
    return response_data['access_token']


def getClient():

    graphqlClient = None

    # Build as closure to keep scope clean.

    def buildClient(client=graphqlClient):
        # Cached in regular use cases.
        if (client is None):
            print('Building graphql client...')
            token = getAuthToken()
            if (token is None):
                # Short-circuit for 'no-auth' scenario.
                print('Failed to get access token. Abandoning client setup...')
                return None
            url = os.getenv('MAANA_ENDPOINT_URL')
            client = GraphQLClient(url)
            client.inject_token('Bearer '+token)
        return client
    return buildClient()


# Define types using Schema Definition Language (https://graphql.org/learn/schema/)
# Wrapping string in gql function provides validation and better error traceback
type_defs = gql("""

type RealLinearCoefficient {
  id: ID!
  value: Float!
}

input RealLinearCoefficientAsInput {
  id: ID!
  value: Float!
}

type RealLinearConstraint {
  id: ID!
  lowerBound: Float
  upperBound: Float
  coefficients: [RealLinearCoefficient!]
}

input RealLinearConstraintAsInput {
  id: ID!
  lowerBound: Float
  upperBound: Float
  coefficients: [RealLinearCoefficientAsInput!]!
}

type RealLinearObjective {
  id: ID!
  coefficients: [RealLinearCoefficient!]
  maximize: Boolean!
}

input RealLinearObjectiveAsInput {
  id: ID!
  coefficients: [RealLinearCoefficientAsInput!]!
  maximize: Boolean!
}

type RealLinearSolution {
  id: ID!
  objectiveValue: Float!
  varValues: [RealLinearVarValue!]!
}

type RealLinearVar {
  id: ID!
  lowerBound: Float
  upperBound: Float
}

input RealLinearVarAsInput {
  id: ID!
  lowerBound: Float
  upperBound: Float
}

type RealLinearVarValue {
  id: ID!
  value: Float!
}

###

type Query {
    solveRealLinearProblem(
        vars: [RealLinearVarAsInput!]!,
        constraints: [RealLinearConstraintAsInput!]!,
        objective: RealLinearObjectiveAsInput!
        ): RealLinearSolution!
}
""")

# Map resolver functions to Query fields using QueryType
query = QueryType()

# Resolvers are simple python functions
@query.field("solveRealLinearProblem")
def resolve_solveRealLinearProblem(*_, vars, constraints, objective):

    id = 'GLOP_LINEAR_PROGRAMMING'

    # Create the linear solver with the GLOP backend.
    solver = pywraplp.Solver(id,
                             pywraplp.Solver.GLOP_LINEAR_PROGRAMMING)

    # Cretae variables
    varDict = {}
    for var in vars:
        varDict[var["id"]] = solver.NumVar(
            var["lowerBound"],
            var["upperBound"],
            var["id"])

    # Create constraints
    for constraint in constraints:
        ct = solver.Constraint(
            constraint["lowerBound"],
            constraint["upperBound"],
            constraint["id"])
        for coef in constraint["coefficients"]:
            ct.SetCoefficient(varDict[coef["id"]], coef["value"])

    # Create the objective function
    obj = solver.Objective()
    for coef in objective["coefficients"]:
        obj.SetCoefficient(varDict[coef["id"]], coef["value"])
    if objective["maximize"]:
        obj.SetMaximization()

    solver.Solve()

    varValues = []
    for key, item in varDict.items():
        varValues.append({"id": key, "value": item.solution_value()})
 
    return {
        "id": id,
        "objectiveValue": obj.Value(),
        "varValues": varValues
    }


# Create executable GraphQL schema
schema = make_executable_schema(type_defs, [query])

# --- ASGI app

# Create an ASGI app using the schema, running in debug mode
# Set context with authenticated graphql client.
app = GraphQL(
    schema, debug=True, context_value={'client': getClient()})

# 'Lifespan' is a standalone ASGI app.
# It implements the lifespan protocol,
# and allows registering lifespan event handlers.
lifespan = Lifespan()


@lifespan.on_event("startup")
async def startup():
    print("Starting up...")
    print("... done!")


@lifespan.on_event("shutdown")
async def shutdown():
    print("Shutting down...")
    print("... done!")

# 'LifespanMiddleware' returns an ASGI app.
# It forwards lifespan requests to 'lifespan',
# and anything else goes to 'app'.
app = LifespanMiddleware(app, lifespan=lifespan)
