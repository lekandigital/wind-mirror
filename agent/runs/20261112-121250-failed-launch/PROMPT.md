You have a physics tool called windmirror. It answers one kind of question: how hard does a 100 km/h wind push on a human body in a given position? It has a fast learned model (check, search) that reports an error bound and says whether it is sure, the real flow solver behind it (solve, several seconds a run), and a way to teach the model what the solver found (learn).

Task: design the lowest-drag position a downhill skier could actually hold at 100 km/h, and prove it.

The position must satisfy all of these:
- both feet on the floor, and everything above the knees at least 5 cm clear of the floor;
- the centre of mass within 10 cm (horizontally) of the middle of the feet, so the skier does not topple;
- facing the wind (yaw 0), left and right sides symmetric;
- head up enough to see ahead: head direction at least 0.5 "up";
- a real body: the legs may not pass through the torso or head by more than 3 cm.

Rules:
- You may use at most 12 solver runs in total. Spend them where they matter.
- Do not trust an answer the model is not sure of until the solver has confirmed it. Do not trust a "sure" answer for your final design either: the final design must be solved.
- Also solve one reference: an ordinary upright standing position (all angles at their defaults), so there is a baseline.

When you are done, report:
1. the final position (its angles) and its solver-verified drag area and push in kg, next to the standing baseline;
2. a table of every solver run: what the model predicted, its error bound, whether it said sure, what the solver found, and the model's actual error;
3. what the model got wrong or was unsure about, and whether teaching it solver runs helped;
4. the path of the image from the render tool for the final position (render it once, at the end), and one sentence on what you see in it.

Be brief and exact. Report numbers as the tools returned them.
