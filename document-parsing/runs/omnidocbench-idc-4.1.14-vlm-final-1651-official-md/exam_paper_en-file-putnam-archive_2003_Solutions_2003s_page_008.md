    where

$$\begin{array}{l} C _ {j} = \# \left\{i <   j: \operatorname{s g n} \left(a _ {i}\right) = \operatorname{s g n} \left(a _ {j}\right) \right\} \\ - \# \{i <   j: \operatorname{s g n} (a _ {i}) \neq \operatorname{s g n} (a _ {j}) \}. \\ \end{array}$$
    Consider the partial sum $P_{k} = \sum_{j = 1}^{k}C_{j}$ . If exactly $p_k$ of $a_1,\ldots ,a_k$ are positive, then this sum is equal to
    $$\binom{p _ {k}} {2} + \binom{k - p _ {k}} {2} - \left[ \binom{k} {2} - \binom{p _ {k}} {2} - \binom{k - p _ {k}} {2} \right],$$
    which expands and simplifies to

        $$- 2 p _ {k} (k - p _ {k}) + \binom{k} {2}.$$
    For $k \leq 2p$ even, this partial sum would be minimized with $p_k = \frac{k}{2}$ , and would then equal $-\frac{k}{2}$ ; for $k < 2p$ odd, this partial sum would be minimized with $p_k = \frac{k \pm 1}{2}$ , and would then equal $-\frac{k - 1}{2}$ . Either way, $P_k \geq -\lfloor \frac{k}{2} \rfloor$ . On the other hand, if $k > 2p$ , then
      $$- 2 p _ {k} (k - p _ {k}) + \binom{k} {2} \geq - 2 p (k - p) + \binom{k} {2}$$
    since $p_k$ is at most $p$. Define $Q_k$ to be $-\left\lfloor \frac{k}{2} \right\rfloor$ if $k \leq 2p$ and $-2p(k - p) + \binom{k}{2}$ if $k \geq 2p$, so that $P_k \geq Q_k$. Note that $Q_1 = 0$.
    Partial summation gives

  $$\begin{array}{l} \sum_ {j = 1} ^ {n} r _ {j} C _ {j} = r _ {n} P _ {n} + \sum_ {j = 2} ^ {n} \left(r _ {j - 1} - r _ {j}\right) P _ {j - 1} \\ \geq r _ {n} Q _ {n} + \sum_ {j = 2} ^ {n} \left(r _ {j - 1} - r _ {j}\right) Q _ {j - 1} \\ = \sum_ {j = 2} ^ {n} r _ {j} \left(Q _ {j} - Q _ {j - 1}\right) \\ = - r _ {2} - r _ {4} - \dots - r _ {2 p} + \sum_ {j = 2 p + 1} ^ {n} (j - 1 - 2 p) r _ {j}. \\ \end{array}$$
It follows that

  $$\begin{array}{l} \sum_ {1 \leq i <   j \leq n} | a _ {i} + a _ {j} | = \sum_ {i = 1} ^ {n} (n - i) r _ {i} + \sum_ {j = 1} ^ {n} r _ {j} C _ {j} \\ \geq \sum_ {i = 1} ^ {2 p} (n - i - [ i \text{even} ]) r _ {i} \\ + \sum_ {i = 2 p + 1} ^ {n} (n - 1 - 2 p) r _ {i} \\ = (n - 1 - 2 p) \sum_ {i = 1} ^ {n} r _ {i} \\ + \sum_ {i = 1} ^ {2 p} (2 p + 1 - i - [ i \text{even} ]) r _ {i} \\ \geq (n - 1 - 2 p) \sum_ {i = 1} ^ {n} r _ {i} + p \sum_ {i = 1} ^ {2 p} r _ {i} \\ \geq (n - 1 - 2 p) \sum_ {i = 1} ^ {n} r _ {i} + p \frac{2 p}{n} \sum_ {i = 1} ^ {n} r _ {i}, \\ \end{array}$$
as desired. The next-to-last and last inequalities each follow from the monotonicity of the $r_i$'s, the former by pairing the $i^\mathrm{th}$ term with the $(2p + 1 - i)^\mathrm{th}$.
Note: Compare the closely related Problem 6 from the 2000 USA Mathematical Olympiad: prove that for any nonnegative real numbers $a_1, \ldots, a_n, b_1, \ldots, b_n$, one has
    $$\sum_ {i, j = 1} ^ {n} \min  \left\{a _ {i} a _ {j}, b _ {i} b _ {j} \right\} \leq \sum_ {i, j = 1} ^ {n} \min  \left\{a _ {i} b _ {j}, a _ {j} b _ {i} \right\}.$$
