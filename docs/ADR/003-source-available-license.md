# ADR-003: Source-Available Licensing Strategy

## Status
Accepted

## Context
LearnFlow AI needs a licensing model that:
1. Encourages open source collaboration and learning
2. Protects against unauthorized commercial exploitation
3. Allows for potential future monetization through SaaS offerings
4. Maintains trust with the developer community

Traditional open source licenses (MIT, Apache 2.0) allow unrestricted commercial use, while proprietary licenses discourage community contribution.

## Decision

### License Choice: Apache 2.0 with Commons Clause

We adopt Apache 2.0 as the base license with Commons Clause 1.0 addition:

```
Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.

"Commons Clause" License Condition v1.0

The Software is provided to you by the Licensor under the License,
as defined below, subject to the following condition.

Without limiting other conditions in the License, the grant of rights
under the License will not include, and the License does not grant to you,
the right to Sell the Software.

For purposes of the foregoing, "Sell" means practicing any or all of the
rights granted to you under the License to provide to third parties,
for a fee or other consideration (including without limitation fees for
hosting or consulting/support services related to the Software),
a product or service whose value derives, entirely or substantially,
from the functionality of the Software.
```

### Why This Combination?

1. **Apache 2.0 Base**
   - Well-understood by developers
   - Patent protection
   - Clear contribution guidelines
   - Compatible with most corporate policies for internal use

2. **Commons Clause Addition**
   - Prevents direct commercialization
   - Allows internal business use
   - Permits educational and research use
   - Enables community contributions

### Permitted Uses

✅ **Allowed:**
- Personal projects and learning
- Academic research and education
- Internal business tools (not sold)
- Contributing improvements back
- Forking for non-commercial purposes
- Building non-commercial applications

❌ **Not Allowed:**
- Selling the software as a service
- Offering paid hosting of LearnFlow AI
- Charging for support/consulting specifically for LearnFlow AI
- Including in commercial products
- Reselling or redistributing for profit

### Alternative Licenses Considered

| License | Pros | Cons | Decision |
|---------|------|------|----------|
| MIT/Apache 2.0 (pure) | Maximum adoption, true OSS | No commercial protection | Rejected |
| AGPL v3 | Strong copyleft, SaaS protection | Too restrictive, scares enterprises | Rejected |
| BSL 1.1 | Time-based commercial protection | Complex, less understood | Rejected |
| Elastic License 2.0 | Good SaaS protection | Not OSI-approved, newer | Rejected |
| PolyForm Noncommercial | Clear non-commercial | Less known, no patent clause | Rejected |

## Implementation

### Repository Structure

```
/
├── LICENSE                    # Apache 2.0 + Commons Clause
├── LICENSE.commons-clause     # Commons Clause text
├── NOTICE                     # Required attributions
├── CONTRIBUTING.md            # CLA requirements
└── docs/
    └── licensing-faq.md       # Clear explanations
```

### Contributor License Agreement (CLA)

Contributors must sign a CLA that:
1. Grants us rights to relicense their contributions
2. Confirms they have rights to contribute
3. Maintains their copyright ownership

### Dual Licensing Strategy

Future commercial offerings:
```
┌─────────────────────────┐
│   LearnFlow AI Core     │
│ (Apache 2.0 + Commons)  │
│   Community Edition     │
└───────────┬─────────────┘
            │
    ┌───────┴────────┐
    ↓                ↓
┌──────────┐    ┌──────────┐
│   SaaS   │    │Enterprise│
│ Platform │    │ License  │
│(Proprietary)  │(Commercial)
└──────────┘    └──────────┘
```

## Consequences

### Positive
- **Protection** - Prevents unauthorized commercialization
- **Flexibility** - Allows future business models
- **Clarity** - Clear terms for users and contributors
- **Community** - Encourages contributions and learning
- **Adoption** - Suitable for internal enterprise use

### Negative
- **Not "True" Open Source** - Not OSI-approved
- **Confusion** - "Source-available" vs "open source"
- **Limited Ecosystem** - Some tools/platforms require OSI licenses
- **Contributor Concerns** - Some may prefer pure open source

### Mitigation
- Clear documentation explaining the license
- FAQ addressing common concerns
- Potential future transition to full open source
- Commercial licenses for specific use cases

## Communication Strategy

### README Badge
```markdown
[![License](https://img.shields.io/badge/License-Apache%202.0%20with%20Commons%20Clause-yellow.svg)](LICENSE)
```

### Clear Messaging
"LearnFlow AI is source-available software. You can use, modify, and distribute it for non-commercial purposes. See our [licensing FAQ](docs/licensing-faq.md) for details."

### FAQ Topics
1. Can I use this in my company?
2. Can I contribute?
3. Can I fork this project?
4. What about academic use?
5. How do I get a commercial license?

## Review Schedule
- 6 months: Assess community reception
- 1 year: Evaluate commercial interest
- 2 years: Consider license changes based on project maturity

## References
- [Commons Clause](https://commonsclause.com/)
- [Apache License 2.0](https://www.apache.org/licenses/LICENSE-2.0)
- [Choose a License](https://choosealicense.com/)
- [OSI on Source-Available](https://opensource.org/node/1099)