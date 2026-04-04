"""GraphQL query and mutation constants for GitHub Projects V2 integration."""

INTROSPECT_PROJECT = """
query IntrospectProject($org: String!, $number: Int!) {
  organization(login: $org) {
    projectV2(number: $number) {
      id
      title
      fields(first: 50) {
        nodes {
          ... on ProjectV2SingleSelectField {
            id
            name
            options {
              id
              name
            }
          }
          ... on ProjectV2Field {
            id
            name
          }
          ... on ProjectV2IterationField {
            id
            name
          }
        }
      }
    }
  }
}
"""

RESOLVE_ISSUE = """
query ResolveIssue($nodeId: ID!) {
  node(id: $nodeId) {
    ... on Issue {
      __typename
      number
      title
      body
      state
      url
      repository {
        name
        owner {
          login
        }
      }
      labels(first: 20) {
        nodes {
          name
        }
      }
      assignees(first: 10) {
        nodes {
          login
        }
      }
    }
    ... on DraftIssue {
      __typename
      title
    }
  }
}
"""

FIND_PROJECT_ITEM = """
query FindProjectItem($issueId: ID!) {
  node(id: $issueId) {
    ... on Issue {
      projectItems(first: 20) {
        nodes {
          id
          project {
            id
          }
          fieldValues(first: 20) {
            nodes {
              ... on ProjectV2ItemFieldSingleSelectValue {
                field {
                  ... on ProjectV2SingleSelectField {
                    name
                  }
                }
                name
                optionId
              }
            }
          }
        }
      }
    }
  }
}
"""

UPDATE_ITEM_FIELD_VALUE = """
mutation UpdateItemFieldValue($input: UpdateProjectV2ItemFieldValueInput!) {
  updateProjectV2ItemFieldValue(input: $input) {
    projectV2Item {
      id
    }
  }
}
"""

ADD_COMMENT = """
mutation AddComment($subjectId: ID!, $body: String!) {
  addComment(input: {subjectId: $subjectId, body: $body}) {
    commentEdge {
      node {
        url
      }
    }
  }
}
"""
