# AI Privacy

The current AI implementation runs locally and sends no student data over the network. It uses complaint title, description, and location type only.

External data sharing is disabled by default with `AI_EXTERNAL_DATA_ALLOWED=false`. Any future external provider must remove names, email addresses, phone numbers, room numbers, and other identifiers before transmission, and must fail back to local analysis on timeout or provider errors.

AI output is a suggestion, not a final administrative decision. Store only the minimum audit information needed to explain and review predictions. Never execute AI-generated SQL, code, HTML, or shell commands.
