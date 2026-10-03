Requested official URL: https://geminicli.com/docs/get-started/authentication
Accessed UTC: 2026-10-03T14:56:47.884176+00:00
Title: Gemini CLI authentication setup | Gemini CLI
Retrieval: documentation extraction; excerpt may be abbreviated. Not a runtime test. Trailing whitespace normalized.

Unpaid tier and Google One users: Gemini CLI was replaced by Antigravity
CLI on June 18th, 2026. To learn more, see our [blog post](https://developers.googleblog.com/an-important-update-transitioning-gemini-cli-to-antigravity-cli) .
Search

...

# Gemini CLI authentication setup
Copy as Markdown
To use Gemini CLI, you’ll need to authenticate with Google. This guide helps you
quickly find the best way to sign in based on your account type and how you’re
using the CLI.
Tip

...

For most users, we recommend starting Gemini CLI and logging in with your
personal Google account.

## Choose your authentication method
Section titled “Choose your authentication method ”
Select the authentication method that matches your situation in the table below:
| User Type / Scenario | Recommended Authentication Method | Google Cloud Project Required |
| AI Studio user with a Gemini API key | Use Gemini API Key | No |
| Google Cloud Vertex AI user | Vertex AI | Yes |
| Headless mode | Use Gemini API Key or |  |
| Vertex AI | No (for Gemini API Key) |  |
| Yes (for Vertex AI) |  |  |

...

### What is my Google account type?
If you are a **Google AI Pro** or **Google AI Ultra** subscriber, use the Google
account associated with your subscription.
To authenticate and use Gemini CLI:
1. Start the CLI:
  Terminal window
  ```
  gemini
  ```
  web browser. Follow the on-screen instructions. Your credentials will be
  cached locally for future sessions.

...

### Do I need to set my Google Cloud project?
Most individual Google accounts (free and paid) don’t require a Google Cloud
project for authentication. However, you’ll need to set a Google Cloud project
when you meet at least one of the following conditions:
* You are using a company, school, or Google Workspace account.
* You are using a Gemini Code Assist license from the Google Developer Program.
* You are using a license from a Gemini Code Assist subscription.

...

## Use Vertex AI
Section titled “Use Vertex AI ”
To use Gemini CLI with Google Cloud’s Vertex AI platform, choose from the
following authentication options:
* A. Application Default Credentials (ADC) using `gcloud` .
* B. Service account JSON key.
* C. Google Cloud API key.

...

### A. Vertex AI - application default credentials (ADC) using `gcloud`
1. Verify you have a Google Cloud project and Vertex AI API is enabled.
  Terminal window
  ```
  gcloud auth application-default login
  ```
2. Configure your Google Cloud Project .
3. Start the CLI:
  Terminal window
  ```
  gemini
  ```
4. Select **Vertex AI** .

#### B. Vertex AI - service account JSON key
Section titled “B. Vertex AI - service account JSON key”
Consider this method of authentication in non-interactive environments, CI/CD
pipelines, or if your organization restricts user-based ADC or API key creation.
If you have previously set `GOOGLE_API_KEY` or `GEMINI_API_KEY` , you must unset
them:
* macOS/Linux
* Windows (PowerShell)
Terminal window
```
unset GOOGLE_API_KEY GEMINI_API_KEY
```
1. [Create a service account and key](https://cloud.google.com/iam/docs/keys-create-delete) and download the provided JSON file. Assign the “Vertex AI User” role to the
service account.
2. Set the `GOOGLE_APPLICATION_CREDENTIALS` environment variable to the JSON
file’s absolute path. For example:
Terminal window
  ```
  # Replace /path/to/your/keyfile.json with the actual path export GOOGLE_APPLICATION_CREDENTIALS = "/path/to/your/keyfile.json"
  ```
+ macOS/Linux
+ Windows (PowerShell)
3. Configure your Google Cloud Project .
4. Start the CLI:
Terminal window
  ```
  gemini
  ```
5. Select **Vertex AI** .

...

#### C. Vertex AI - Google Cloud API key
1. Obtain a Google Cloud API key: [Get an API Key](https://cloud.google.com/vertex-ai/generative-ai/docs/start/api-keys?usertype=newuser) .
2. Set the `GOOGLE_API_KEY` environment variable:
Terminal window
  ```
  # Replace YOUR_GOOGLE_API_KEY with your Vertex AI API key export GOOGLE_API_KEY = "YOUR_GOOGLE_API_KEY"
  ```

...

## Set your Google Cloud project
When you sign in using your Google account, you may need to configure a Google
Cloud project for Gemini CLI to use. This applies when you meet at least one of
the following conditions:
* You are using a Company, School, or Google Workspace account.
* You are using a Gemini Code Assist license from the Google Developer Program.
* You are using a license from a Gemini Code Assist subscription.

...

1. [Find your Google Cloud Project ID](https://support.google.com/googleapi/answer/7014113) .
2. [Enable the Gemini for Cloud API](https://cloud.google.com/gemini/docs/discover/set-up-gemini) .
3. [Configure necessary IAM access permissions](https://cloud.google.com/gemini/docs/discover/set-up-gemini) .
4. Configure your environment variables. Set either the `GOOGLE_CLOUD_PROJECT` or `GOOGLE_CLOUD_PROJECT_ID` variable to the project ID to use with Gemini
CLI. Gemini CLI checks for `GOOGLE_CLOUD_PROJECT` first, then falls back to `GOOGLE_CLOUD_PROJECT_ID` .
For example, to set the `GOOGLE_CLOUD_PROJECT_ID` variable:
Terminal window
  ```
  # Replace YOUR_PROJECT_ID with your actual Google Cloud project ID export GOOGLE_CLOUD_PROJECT = "YOUR_PROJECT_ID"
  ```
To make this setting persistent, see Persisting Environment Variables .
+ macOS/Linux
+ Windows (PowerShell)

...

## Running in Google Cloud environments
Section titled “Running in Google Cloud environments ”
When running Gemini CLI within certain Google Cloud environments, authentication
is automatic.
In a Google Cloud Shell environment, Gemini CLI typically authenticates
automatically using your Cloud Shell credentials. In Compute Engine
environments, Gemini CLI automatically uses Application Default Credentials
(ADC) from the environment’s metadata server.
If automatic authentication fails, use one of the interactive methods described
on this page.

## Running in headless mode
Section titled “Running in headless mode ”
[Headless mode](https://geminicli.com/docs/cli/headless) will use your existing authentication
method, if an existing authentication credential is cached.
If you have not already signed in with an authentication credential, you must
configure authentication using environment variables:
* Use Gemini API Key
* Vertex AI

## What’s next?
Section titled “What’s next?”
Your authentication method affects your quotas, pricing, Terms of Service, and
privacy notices. Review the following pages to learn more:
* [Gemini CLI: Quotas and Pricing](https://geminicli.com/docs/resources/quota-and-pricing) .
* [Gemini CLI: Terms of Service and Privacy Notice](https://geminicli.com/docs/resources/tos-privacy) .
Last updated: Sep 18, 2026
