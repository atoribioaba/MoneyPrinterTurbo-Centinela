# F34 · Retention Intelligence

Version: `retention-intelligence-v0.1`.

F34 is descriptive, not causal. It consumes verified normalized retention
points and reports:

- mean of available points through the first 10% of the timeline;
- nearest observed midpoint;
- final observed ratio;
- largest observed point-to-point drop and its position.

It does not interpolate missing points and does not say *why* viewers left.
Recommendations are deliberately deferred to an experiment-planning phase.

YouTube's Analytics API documents `elapsedVideoTimeRatio` and
`audienceWatchRatio`; the API can expose 100 retention positions for a video.
