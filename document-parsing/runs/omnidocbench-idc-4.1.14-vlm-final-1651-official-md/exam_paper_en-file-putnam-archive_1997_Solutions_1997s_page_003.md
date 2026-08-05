    we have

  $$\begin{array}{l} s _ {k} - s _ {k - 1} + s _ {k + 2} = \sum_ {i} (- 1) ^ {i} \left(a _ {n - i, i} + a _ {n - i, i + 1} + a _ {n - i, i + 2}\right) \\ = \sum_ {i} (- 1) ^ {i} a _ {n - i + 1, i + 2} = s _ {k + 3}. \\ \end{array}$$
    By computing $s_0 = 1, s_1 = 1, s_2 = 0$, we may easily verify by induction that $s_{4j} = s_{4j+1} = 1$ and $s_{4j+2} = s_{4j+3} = 0$ for all $j \geq 0$. (Alternate solution suggested by John Rickert: write $S(x,y) = \sum_{i=0}^{\infty} (y + xy^2 + x^2 y^3)^i$, and note note that $s_k$ is the coefficient of $y^k$ in $S(-1,y) = (1+y)/(1-y^4)$.)
B-5 Define the sequence $x_{1} = 2$, $x_{n} = 2^{x_{n - 1}}$ for $n > 1$. It suffices to show that for every $n$, $x_{m} \equiv x_{m + 1} \equiv \dots \pmod{n}$ for some $m < n$. We do this by induction on $n$, with $n = 2$ being obvious.
    Write $n = 2^a b$, where $b$ is odd. It suffices to show that $x_{m} \equiv \dots$ modulo $2^{a}$ and modulo $b$, for some $m < n$. For the former, we only need $x_{n-1} \geq a$, but clearly $x_{n-1} \geq n$ by induction on $n$. For the latter, note that $x_{m} \equiv x_{m+1} \equiv \dots \pmod{b}$ as long as $x_{m-1} \equiv x_{m} \equiv \dots \pmod{\phi(b)}$, where $\phi(n)$ is the Euler totient function. By hypothesis, this occurs for some $m < \phi(b) + 1 \leq n$. (Thanks to Anoop Kulkarni for catching a lethal typo in an earlier version.)
B-6 The answer is 25 / 13 . Place the triangle on the cartesian plane so that its vertices are at C = (0,0), A = (0,3), B = (4,0) . Define also the points D = (20 / 13, 24 / 13) , and E = (27 / 13, 0) . We then compute that

      $$\begin{array}{l} \frac{2 5}{1 3} = A D = B E = D E \\ \frac{2 7}{1 3} = B C - C E = B E <   B C \\ \frac{3 9}{1 3} = A C <   \sqrt{A C ^ {2} + C E ^ {2}} = A E \\ \frac{4 0}{1 3} = A B - A D = B D <   A B \\ \end{array}$$
and that AD < CD . In any dissection of the triangle into four parts, some two of A,B,C,D,E must belong to the same part, forcing the least diameter to be at least 25/13.

We now exhibit a dissection with least diameter 25 / 13 . (Some variations of this dissection are possible.) Put F = (15 / 13,19 / 13) , G = (15 / 13,0) , H = (0,19 / 13) , J = (32 / 15,15 / 13) , and divide ABC into the convex polygonal regions ADFH, BEJ, CGFH, DFGEJ. To check that this dissection has least diameter 25 / 13 , it suffices (by the following remark) to check that the distances

    $$A D, A F, A H, B E, B J, D E, C F, C G, C H,$$
  $$D F, D G, D H, D J, E F, E G, E J, F G, F H, F J, G J$$
are all at most $25/13$. This can be checked by a long numerical calculation, which we omit in favor of some shortcuts: note that $ADFH$ and $BEJ$ are contained in circular sectors centered at $A$ and $B$, respectively, of radius $25/13$ and angle less than $\pi/3$, while $CGFH$ is a rectangle with diameter $CF < 25/13$.
Remark. The preceding argument uses implicitly the fact that for $P$ a simple closed polygon in the plane, if we let $S$ denote the set of points on or within $P$, then the maximum distance between two points of $S$ occurs between some pair of vertices of $P$. This is an immediate consequence of the compactness of $S$ (which guarantees the existence of a maximum) and the convexity of the function taking $(x,y) \in S \times S$ to the squared distance between $x$ and $y$ (which is obvious in terms of Cartesian coordinates).
