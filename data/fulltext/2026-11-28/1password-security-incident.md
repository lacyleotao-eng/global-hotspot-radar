[Skip to Main Content](https://1password.com/blog/update-on-nov-2026-security-incident#main)
[1Password for Agents: Give AI Agents access, not your passwords. Learn more](https://1password.com/personal-ai-agent-integrations)
[Sign in](https://start.1password.com/signin?l=en)
[![1Password](https://images.ctfassets.net/2h488pz7kgfv/4rqwpt3FlpOV8FLnsAZP1D/55b55585418645e5d298be37655bbdd8/1Password_Logo.svg)](https://1password.com/)
[Sign in](https://start.1password.com/signin?l=en)[Get started free](https://1password.com/pricing/enterprise)
[Back to blog](https://1password.com/blog)
# Update on a security incident involving 1Password’s backend systems. Customer vaults were not affected and all vault contents remain secure.
![](https://images.ctfassets.net/3091ajzcmzlr/DjtrukPcrZdJZjXdIqlhU/224c70b47b1012bd2d4067ba565b0c9b/1password.jpg?w=3840&q=70&fm=avif)
by 1Password
November 25, 2026 - 4 min
![](https://images.ctfassets.net/3091ajzcmzlr/3yu0DTU3edoU7HK8MxkW54/c5e7801fb8c0d7d52295da96af7e8013/business_2x.webp?w=3840&q=70&fm=avif)
## Related Categories
  * [Security](https://1password.com/blog/categories/security)


**Update: We will be providing a Root Cause Analysis (RCA) with details in the coming weeks once our full investigation is complete.**
## **The short version**
  * An attacker gained access to some of our backend systems and copied a limited amount of customer account information from a subset of our customers, including the names and email addresses that customers use to sign into 1Password.
  * **Your vault data, the items in them, and the keys that protect them are safe and were not affected.** 1Password does not have access to your password or secret keys. 
  * We implemented containment measures, restored clean versions of the affected service, and have triggered a rotation of internal credentials. 
  * You do not need to update anything in your 1Password account.
  * We recommend being cautious of phishing attempts in the form of unexpected emails about 1Password, such as invitations or account recovery requests that you did not initiate.
  * 1Password apps and services are working normally.


## **What happened**
On November 19, 2026, 1Password began investigating indications that an attacker gained access to an employee’s corporate GitHub account. The actor used the account to access source code and push malicious code to backend services, which downloaded administrative data pertaining to our customers. This data included customer names and email addresses, in addition to non-secret internal metadata about the account. At no time were customer vault contents accessed by, or available to, the attacker.
## **What information was affected**
The attacker downloaded account records for a subset of our users. These records include:
  * Names and email addresses
  * Account and user identifiers, and account creation and last sign-in times
  * Public keys (which are public by design, this has no impact to user security)
  * [Secure Remote Password](https://1password.com/blog/developers-how-we-use-srp-and-you-can-too) protocol parameters (which cannot be used to access your account) 
  * Tokens present in certain emailed links for invitations, provisioning and account recovery
  * Other non-secret account metadata relative to our internal architecture (e.g. version numeric identifiers, file numeric identifiers)


The attacker also copied source code from private repositories and gained access to our CI/CD system. Our source code is not customer data, and contains no user secrets. CI/CD contains infrastructure related secrets in order for our product to work. We have triggered a rotation of all credentials which may have been exposed, and there is no impact to 1Password’s services, availability, or product security. 
When we send an email to a customer to accept a provisioning invite to an account, or to accept recovery of their account, it contains a token. A provisioning invite is specifically used for our [SCIM Bridge](https://support.1password.com/cs/scim/) or [Hosted Provisioning](https://support.1password.com/provisioning/). During this incident there were a small number of users in this state, who have been specifically notified. This token is used to complete the invitation or recovery process, but only when combined with an SSO sign-in or a six digit code sent to the user's registered email address. The token is not able to get access to the account by itself. In order to reduce the ability for a malicious third party to successfully guess the code, we’ve expanded the code from six numeric digits to ten alphanumeric digits. This makes brute force guessing practically impossible.
## **What was not affected**
  * Your vaults and the items in them
  * The keys that protect your vaults 
    * 1Password does not store your account password or secret key
  * Account recovery keys
  * 1Password apps and browser extensions


## **What we’ve done**
  * Disabled the affected GitHub account, revoked the stolen token, and removed the access the attacker created.
  * Rotated or revoked all internal credentials which may have been exposed.
  * Lengthened the codes used in invitation and recovery emails from six digits to ten characters as a precautionary measure.
  * Tightened internal GitHub, CI/CD, and endpoint controls, and added new detections for this kind of attack.
  * Validated no internal evidence of user account takeovers or compromise using any exposed account provisioning tokens. 
  * Brought in independent cybersecurity experts to validate our containment approaches and remediation efforts.


## **What you can do**
  * Be cautious about phishing attempts in the form of unexpected emails, texts or calls that mention 1Password, invitations, or account recovery attempts. 
  * 1Password will never contact you to ask for your account password or Secret Key. Only enter them in the official 1Password app, or on our official website, and only when you’ve opened the app or typed the address yourself. Your Secret Key is only needed the first time you sign in on a new device or browser. 
  * Keep your Secret Key and account password safe.
  * If you see something suspicious, tell us at support@1password.com.


## **Our commitment to you**
You trust us with some of the most sensitive information you have. 1Password is designed so that a breach of our systems can’t expose your vault contents. Your vault secrets are encrypted with keys that only you hold, so we can’t access them, and neither can an attacker who gets into our servers. 
We are committed to transparency in the interests of our customers' security and the security of the broader industry, which is why we have published and maintained our [Security Whitepaper](https://agilebits.github.io/security-design/) since 2015. We’ll keep this blog post current, and we’ll update it if we find anything that changes what we’ve said here. 
###### Downloads
  * [macOS](https://1password.com/downloads/mac)
  * [Windows](https://1password.com/downloads/windows)
  * [iOS](https://1password.com/downloads/ios)
  * [Android](https://1password.com/downloads/android)
  * [Browser](https://1password.com/downloads/browser-extension)
  * [Linux](https://1password.com/downloads/linux)
  * [CLI](https://1password.com/downloads/command-line)


###### 1Password for
  * [Individuals and families](https://1password.com/personal-family-security)
  * [Small business](https://1password.com/product/teams-small-business-password-manager)
  * [Business](https://1password.com/business-security)
  * [Enterprise](https://1password.com/enterprise-security)
  * [Developers](https://1password.com/developer-security)
  * [MSPs](https://1password.com/managed-service-provider-security)
  * [Students](https://www.studentbeans.com/en-us/us/beansid-connect/hosted/1password)


###### Industries
  * [Consumer goods](https://1password.com/industry/consumer-goods)
  * [SaaS and technology](https://1password.com/industry/saas-and-technology)
  * [Financial services](https://1password.com/industry/financial-services)


###### Developers
  * [Developer documentation](https://1password.dev/)
  * [Developer community](https://www.1password.dev/community)
  * [Bug bounty](https://hackerone.com/1password)


###### Platform
  * [Unified Access Platform](https://1password.com/platform)
  * [Plans and pricing](https://1password.com/pricing/enterprise)
  * [Watch demos](https://1password.com/demos)
  * [Integrations](https://marketplace.1password.com/)


###### Features
  * [Autofill](https://1password.com/features/autofill)
  * [Access reviews](https://1password.com/features/access-reviews)
  * [Access requests](https://1password.com/features/access-requests)
  * [Credential governance](https://1password.com/features/credential-governance)
  * [License management](https://1password.com/features/software-license-management)
  * [Watchtower insights](https://1password.com/features/watchtower-identifies-security-risks)
  * [Developer Watchtower](https://1password.com/features/developer-watchtower)
  * [Password sharing](https://1password.com/features/secure-password-sharing)
  * [Two-factor authentication](https://1password.com/features/two-factor-authentication)
  * [Passwordless](https://1password.com/solutions/passwordless)
  * [All features](https://1password.com/features)


###### Products 
  * [Password manager](https://1password.com/product/password-manager)
  * [Enterprise Password Manager](https://1password.com/product/enterprise-password-manager)
  * [Privileged Access](https://1password.com/product/privileged-access)
  * [SaaS Manager](https://1password.com/product/saas-manager)
  * [Credential Broker](https://1password.com/product/credential-broker)
  * [Device Trust](https://1password.com/product/device-trust)


###### Solutions
  * [Zero standing privileges](https://1password.com/solutions/zero-standing-privileges)
  * [Just-in-time access](https://1password.com/solutions/just-in-time-access)
  * [Agentic AI security](https://1password.com/solutions/agentic-ai)
  * [AI agent identity](https://1password.com/solutions/ai-agent-identity)
  * [Secrets management](https://1password.com/features/secrets-management)
  * [Credential management](https://1password.com/solutions/credential-management)
  * [SaaS lifecycle management](https://1password.com/solutions/saas-onboarding-offboarding)
  * [AI spend management](https://1password.com/solutions/ai-spend-management)
  * [Shadow IT discovery](https://1password.com/solutions/shadow-it)
  * [Compliance](https://1password.com/solutions/cybersecurity-compliance)


###### Resources
  * [Blog](https://1password.com/blog)
  * [Webinars](https://1password.com/webinars)
  * [Security research](https://1password.com/research)
  * [Customer stories](https://1password.com/customer-stories)
  * [Resource library](https://1password.com/resources)


###### Partners
  * [Explore partners](https://1password.com/partnerships)
  * [Become a partner](https://1password.com/contact-sales/partners)
  * [Password Manager MSP edition](https://1password.com/product/enterprise-password-manager-msp-edition)
  * [Partner portal](https://www.1password.partners/)


###### Company
  * [About](https://1password.com/company)
  * [We're hiring!](https://1password.com/careers)
  * [Press](https://1password.com/press)
  * [Newsletter](https://1password.com/newsletter)
  * [Legal Center](https://1password.com/legal)
  * [Trust Center](https://trust.1password.io/)
  * [Privacy](https://1password.com/legal/privacy)
  * [Security](https://1password.com/security)


###### Support
  * [Help and documentation](https://support.1password.com/)
  * [Customer support](https://1password.com/contact-support)
  * [Community](https://www.1password.community/)
  * Privacy support


###### Downloads
  * [macOS](https://1password.com/downloads/mac)
  * [Windows](https://1password.com/downloads/windows)
  * [iOS](https://1password.com/downloads/ios)
  * [Android](https://1password.com/downloads/android)
  * [Browser](https://1password.com/downloads/browser-extension)
  * [Linux](https://1password.com/downloads/linux)
  * [CLI](https://1password.com/downloads/command-line)


[](https://1password.com/)
[Terms of Service](https://1password.com/legal/terms-of-service)
[Cookie Policy](https://1password.com/legal/cookie-policy)
Your Privacy ChoicesCalifornia Consumer Privacy Act (CCPA) Opt-Out Icon
[Privacy Policy](https://1password.com/legal/privacy)
[Accessibility](https://1password.com/legal/accessibility)
[Sitemap](https://1password.com/sitemap)
© 2026 1Password. All rights reserved.
4711 Yonge St, 10th Floor, Toronto Ontario, M2N 6K8, Canada
  * [![](https://images.ctfassets.net/2h488pz7kgfv/oJlDSiCmOdAQxi4vImlrG/d530d9d5b1742e744fc4ff111369ee84/x.svg)](https://twitter.com/1Password "1Password on X")
  * [![](https://images.ctfassets.net/2h488pz7kgfv/3VYIGSnfYJPuT9gTAgtbWc/1ef11322bc354e52fc0a2b458260a740/mastodon.svg)](https://1password.social/@1password "1Password on Mastodon")
  * [![](https://images.ctfassets.net/2h488pz7kgfv/71W3zHPvevpPeHtCdklxaw/443bb8480c41290bd580bd3fdb3e5954/reddit.svg)](https://www.reddit.com/r/1Password "1Password on Reddit")
  * [![](https://images.ctfassets.net/2h488pz7kgfv/5DZiwpeDshvc5XGWZKp4ar/d85e5eefbe2edf964c455950560845cc/youtube.svg)](https://www.youtube.com/1PasswordVideos "1Password on YouTube")
  * [![](https://images.ctfassets.net/2h488pz7kgfv/7ATY2kmuBXyjv4jo8FQuSd/f32644cfac516ce5208801fe35f73ed8/github.svg)](https://github.com/1Password "1Password on GitHub")
  * [![](https://images.ctfassets.net/2h488pz7kgfv/19IxpZRO1iVuUMxvg35nOu/7e03ded4a4801b812db1cd611300c357/linkedin.svg)](https://www.linkedin.com/company/1password/ "1Password on LinkedIn")
  * [![](https://images.ctfassets.net/2h488pz7kgfv/7xkjXPoIUrFc3sDvs9S4eg/2e5f3d5673202b26ee5c8fc7b9f678bc/instagram.svg)](https://www.instagram.com/1password/ "1Password on Instagram")
  * [![](https://images.ctfassets.net/2h488pz7kgfv/vJtc67AkiWiNnQzpUfZsd/b46a5e61015b9835edf150eb6b3fb30f/rss.svg)](https://blog.1password.com/index.xml "1Password RSS")


