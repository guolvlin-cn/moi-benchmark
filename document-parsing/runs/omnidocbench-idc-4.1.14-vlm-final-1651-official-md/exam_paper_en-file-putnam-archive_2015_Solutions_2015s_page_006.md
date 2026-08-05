  Similarly,

      $$\begin{array}{l} S _ {2} = \sum_ {c = 1} ^ {\infty} \sum_ {b = c + 1} ^ {\infty} \frac{2 ^ {b + c} - 2 ^ {b - c + 1}}{3 ^ {b} 5 ^ {c}} \\ = \sum_ {c = 1} ^ {\infty} \left(\left(\left(\frac{2}{5}\right) ^ {c} - \frac{2}{1 0 ^ {c}}\right) \sum_ {b = c + 1} ^ {\infty} \left(\frac{2}{3}\right) ^ {b}\right) \\ = \sum_ {c = 1} ^ {\infty} \left(\left(\frac{2}{5}\right) ^ {c} - \frac{2}{1 0 ^ {c}}\right) 3 \left(\frac{2}{3}\right) ^ {c + 1} \\ = \sum_ {c = 1} ^ {\infty} \left(2 \left(\frac{4}{1 5}\right) ^ {c} - 4 \left(\frac{1}{1 5}\right) ^ {c}\right) \\ = \frac{3 4}{7 7}. \\ \end{array}$$
  We conclude that $S = S_{1} + S_{2} = \frac{17}{21}$.
  Second solution: Recall that the real numbers a, b, c form the side lengths of a triangle if and only if

            $$s - a, s - b, s - c > 0 \quad s = \frac{a + b + c}{2},$$
  and that if we put x = 2(s - a), y = 2(s - b), z = 2(s - c) ,

          $$a = \frac{y + z}{2}, b = \frac{z + x}{2}, c = \frac{x + y}{2}.$$
  To generate all integer triples (a,b,c) which form the side lengths of a triangle, we must also assume that x,y,z are either all even or all odd. We may therefore write the original sum as

        $$\sum_ {x, y, z > 0 \text{odd}} \frac{2 ^ {(y + z) / 2}}{3 ^ {(z + x) / 2} 5 ^ {(x + y) / 2}} + \sum_ {x, y, z > 0 \text{even}} \frac{2 ^ {(y + z) / 2}}{3 ^ {(z + x) / 2} 5 ^ {(x + y) / 2}}.$$
  To unify the two sums, we substitute in the first case $x = 2u + 1$, $y = 2v + 1$, $z = 2w + 1$ and in the second case $x = 2u + 2$, $y = 2v + 2$, $z = 2w + 2$ to obtain
    $$\begin{array}{l} \sum_ {(a, b, c) \in T} \frac{2 ^ {a}}{3 ^ {b} 5 ^ {c}} = \sum_ {u, v, w = 1} ^ {\infty} \frac{2 ^ {v + w}}{3 ^ {w + u} 5 ^ {u + v}} \left(1 + \frac{2 ^ {- 1}}{3 ^ {- 1} 5 ^ {- 1}}\right) \\ = \frac{1 7}{2} \sum_ {u = 1} ^ {\infty} \left(\frac{1}{1 5}\right) ^ {u} \sum_ {v = 1} ^ {\infty} \left(\frac{2}{5}\right) ^ {v} \sum_ {w = 1} ^ {\infty} \left(\frac{2}{3}\right) ^ {w} \\ = \frac{1 7}{2} \frac{1 / 1 5}{1 - 1 / 1 5} \frac{2 / 5}{1 - 2 / 5} \frac{2 / 3}{1 - 2 / 3} \\ = \frac{1 7}{2 1}. \\ \end{array}$$
B5 The answer is 4.

  Assume $n \geq 3$ for the moment. We write the permutations $\pi$ counted by $P_{n}$ as sequences $\pi(1), \pi(2), \ldots, \pi(n)$. Let $U_{n}$ be the number of permutations counted by $P_{n}$ that end with $n-1, n$; let $V_{n}$ be the number ending in $n, n-1$; let $W_{n}$ be the number starting with $n-1$ and ending in $n-2, n$; let $T_{n}$ be the number ending in $n-2, n$ but not starting with $n-1$; and let $S_{n}$
  be the number which has $n-1,n$ consecutively in that order, but not at the beginning or end. It is clear that every permutation $\pi$ counted by $P_{n}$ either lies in exactly one of the sets counted by $U_{n}, V_{n}, W_{n}, T_{n}, S_{n}$, or is the reverse of such a permutation. Therefore
    $$P _ {n} = 2 \left(U _ {n} + V _ {n} + W _ {n} + T _ {n} + S _ {n}\right).$$
  By examining how each of the elements in the sets counted by $U_{n+1}, V_{n+1}, W_{n+1}, T_{n+1}, S_{n+1}$ can be obtained from a (unique) element in one of the sets counted by $U_n, V_n, W_n, T_n, S_n$ by suitably inserting the element $n+1$, we obtain the recurrence relations
        $$U _ {n + 1} = U _ {n} + W _ {n} + T _ {n},$$
        $$V _ {n + 1} = U _ {n},$$
        $$W _ {n + 1} = W _ {n},$$
        $$T _ {n + 1} = V _ {n},$$
        $$S _ {n + 1} = S _ {n} + V _ {n}.$$
  Also, it is clear that $W_{n} = 1$ for all $n$.
  So far we have assumed $n \geq 3$, but it is straightforward to extrapolate the sequences $P_{n}, U_{n}, V_{n}, W_{n}, T_{n}, S_{n}$ back to $n = 2$ to preserve the preceding identities. Hence for all $n \geq 2$,

$$\begin{array}{l} P _ {n + 5} = 2 \left(U _ {n + 5} + V _ {n + 5} + W _ {n + 5} + T _ {n + 5} + S _ {n + 5}\right) \\ = 2 \left(\left(U _ {n + 4} + W _ {n + 4} + T _ {n + 4}\right) + U _ {n + 4} \right. \\ + W _ {n + 4} + V _ {n + 4} + \left(S _ {n + 4} + V _ {n + 4}\right)) \\ = P _ {n + 4} + 2 \left(U _ {n + 4} + W _ {n + 4} + V _ {n + 4}\right) \\ = P _ {n + 4} + 2 \left(\left(U _ {n + 3} + W _ {n + 3} + T _ {n + 3}\right) + W _ {n + 3} + U _ {n + 3}\right) \\ = P _ {n + 4} + P _ {n + 3} + 2 \left(U _ {n + 3} - V _ {n + 3} + W _ {n + 3} - S _ {n + 3}\right) \\ = P _ {n + 4} + P _ {n + 3} + 2 \left(\left(U _ {n + 2} + W _ {n + 2} + T _ {n + 2}\right) - U _ {n + 2} \right. \\ + W _ {n + 2} - \left(S _ {n + 2} - V _ {n + 2}\right)) \\ = P _ {n + 4} + P _ {n + 3} + 2 \left(2 W _ {n + 2} + T _ {n + 2} - S _ {n + 2} - V _ {n + 2}\right) \\ = P _ {n + 4} + P _ {n + 3} + 2 \left(2 W _ {n + 1} + V _ {n + 1} \right. \\ - \left(S _ {n + 1} + V _ {n + 1}\right) - U _ {n + 1}) \\ = P _ {n + 4} + P _ {n + 3} + 2 \left(2 W _ {n} + U _ {n} - \left(S _ {n} + V _ {n}\right) - U _ {n} \right. \\ - \left(U _ {n} + W _ {n} + T _ {n}\right)) \\ = P _ {n + 4} + P _ {n + 3} - P _ {n} + 4, \\ \end{array}$$
  as desired.

  Remark: There are many possible variants of the above solution obtained by dividing the permutations up according to different features. For example, Karl Mahlburg suggests writing

      $$P _ {n} = 2 P _ {n} ^ {\prime}, \quad P _ {n} ^ {\prime} = Q _ {n} ^ {\prime} + R _ {n} ^ {\prime}$$
  where $P_{n}^{\prime}$ counts those permutations counted by $P_{n}$ for which 1 occurs before 2, and $Q_{n}^{\prime}$ counts those permutations counted by $P_{n}^{\prime}$ for which $\pi(1) = 1$. One then has the recursion
        $$Q _ {n} ^ {\prime} = Q _ {n - 1} ^ {\prime} + Q _ {n - 3} ^ {\prime} + 1$$
