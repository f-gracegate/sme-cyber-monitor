# Pilot programme (Phase 7)

The goal: a controlled pilot with 5–10 Ghanaian businesses from different sectors before public
launch. It should show that customers understand the product, use it, and are willing to pay,
not only that the software works.

## Who

| Pilot business | What we validate |
| --- | --- |
| Online retailer | Website, domain and e-commerce security, payment flows |
| Accounting firm | Endpoint, identity and sign-in events |
| School | Many users, shared computers and servers |
| Hotel | Network collector and workstation monitoring |
| Small professional services firm | Asset management, reporting and the monthly summary |

## How each pilot runs (6–8 weeks)

1. **Kick-off (week 0):** create the workspace together. The getting-started checklist is the
   agenda: profile, first website, ownership proof, first results, team, MFA, then agents, the
   mobile app and the plan.
2. **Agents and collector (weeks 1–2):** install on a representative set of machines. Note
   install failures in the feedback inbox.
3. **Live use (weeks 2–6):** the customer handles alerts themselves. When resolving, they
   answer "What was it?". "Not a real problem" answers are how we measure false positives.
4. **Weekly 20-minute check-in:** go through the pilot measurements and the customer's
   feedback.
5. **Close (weeks 6–8):** ask them to pay for the plan that fits. Converting, or not, is the
   willingness-to-pay measure.

Pilot workspaces start on the 14-day trial. There is no admin screen for extending trials or
giving free plans yet; a developer can extend a pilot's `subscriptions.current_period_end` in
the database. Record each one, so it isn't counted as a paying customer.

## What we measure

The **Platform → Pilot measurements** table computes these per organisation from live data
(counts and timings only, no customer content):

| Measure (product plan) | How it's computed | Target |
| --- | --- | --- |
| Assets successfully monitored | Active assets with a successful check or agent report / all active assets | ≥ 90% |
| Agent installation success | Agents reporting in the last hour / agents enrolled | ≥ 95% |
| Accuracy of findings / false-positive rate | Alerts resolved as "Not a real problem" / alerts resolved by a person | ≤ 15% |
| Alert delivery time | Load-tested: detection to visible alert in under a second (target 2 minutes) | < 2 min |
| Time to acknowledge / resolve | Median from first seen to acknowledged / resolved (auto-cleared excluded) | Track the trend |
| Dashboard usage | People active in the last 7 days / members | ≥ 50% weekly |
| Willingness to pay | Subscription paid at the end of the pilot | ≥ 50% of pilots |

Qualitative input comes from the in-product **feedback button** (idea, problem, question,
praise, with an optional 1–5 usefulness rating). It lands in **Platform → Customer feedback**,
where the team marks it reviewed or done.

## Feeding results back

- Rules with many "Not a real problem" answers get tuned or reclassified. Muted-alert rules
  show which ones customers find noisy.
- Problems from feedback become issues. Fix them during the pilot, in small releases.
- Before launch, write a short pilot report for each sector (coverage, accuracy, usage,
  conversion, quotes) to validate the plan prices.
