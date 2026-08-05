10. Proof. We omit (a) since is standard. For (b), if u attains an interior maximum, then the conclusion follows from strong maximum principle.

  If not, then for some $x^0 \in \partial U$, $u(x^0) > u(x)$ $\forall x \in U$. Then Hopf's lemma implies $\frac{\partial u}{\partial \nu}(x^0) > 0$, which is a contradiction.
  Remark 2. A generalization of this problem to mixed boundary conditions is recorded in Gilbarg-Trudinger, Elliptic PDEs of second order, Problem 3.1.

11. Proof. Define

          $$B [ u, v ] = \int_ {U} \sum_ {i, j} a ^ {i j} u _ {x _ {i}} v _ {x _ {j}} d x \text{for} u \in H ^ {1} (U), v \in H _ {0} ^ {1} (U).$$
  By Exercise 5.17, $\phi(u) \in H^{1}(U)$. Then, for all $v \in C_{c}^{\infty}(U)$, $v \geq 0$,
        $$\begin{array}{l} B [ \phi (u), v ] = \int_ {U} \sum_ {i, j} a ^ {i j} (\phi (u)) _ {x _ {i}} v _ {x _ {j}} d x \\ = \int_ {U} \sum_ {i, j} a ^ {i j} \phi^ {\prime} (u) u _ {x _ {i}} v _ {x _ {j}} d x, (\phi^ {\prime} (u) \text{isboundedsinceuisbounded}) \\ = \int_ {U} \sum_ {i, j} a ^ {i j} u _ {x _ {i}} \left(\phi^ {\prime} (u) v\right) _ {x _ {j}} - \sum_ {i, j} a _ {i j} \phi^ {\prime \prime} (u) u _ {x _ {i}} u _ {x _ {j}} \text{vdx} \\ \leq 0 - \int_ {U} \phi^ {\prime \prime} (u) v | D u | ^ {2} d x \leq 0, \text{by} \\ \end{array}$$
  (We don't know whether the product of two $H^1$ functions is weakly differentiable. This is why we do not take $v \in H_0^1$. ) Now we complete the proof with the standard density argument.
12. Proof. Given $u \in C^2(U) \cap C(\bar{U})$ with $Lu \leq 0$ in $U$ and $u \leq 0$ on $\partial U$. Since $\bar{U}$ is compact and $v \in C(\bar{U})$, $v \geq c > 0$. So $w := \frac{u}{v} \in C^2(U) \cap C(\bar{U})$. Brutal computation gives us
    $$\begin{array}{l} - a ^ {i j} w _ {x _ {i} x _ {j}} = \frac{- a ^ {i j} u _ {x _ {i} x _ {j}} v + a ^ {i j} v _ {x _ {i} x _ {j}} u}{v ^ {2}} + \frac{a ^ {i j} v _ {x _ {i}} u _ {x _ {j}} - a ^ {i j} u _ {x _ {i}} v _ {x _ {j}}}{v ^ {2}} - a ^ {i j} \frac{2}{v} v _ {x _ {j}} \frac{v _ {x _ {i}} u - v u _ {x _ {i}}}{v ^ {2}} \\ = \frac{\left(L u - b ^ {i} u _ {x _ {i}} - c u\right) v + \left(- L v + b ^ {i} v _ {x _ {i}} + c v\right) u}{v ^ {2}} + 0 + a ^ {i j} \frac{2}{v} v _ {x _ {j}} w _ {x _ {i}}, \text{since} a ^ {i j} = a ^ {j i}. \\ = \frac{L u}{v} - \frac{u L v}{v ^ {2}} - b ^ {i} w _ {x _ {i}} + a ^ {i j} \frac{2}{v} v _ {x _ {j}} w _ {x _ {i}} \\ \end{array}$$
  Therefore,

      $$\text{Mw}:= - a ^ {i j} w _ {x _ {i} x _ {j}} + w _ {x _ {i}} \left[ b ^ {i} - a ^ {i j} \frac{2}{v} v _ {x _ {j}} \right] = \frac{L u}{v} - \frac{u L v}{v ^ {2}} \leq 0 \text{on} \{x \in \bar{U}: u > 0 \} \subseteq U$$
  If $\{x \in \bar{U} : u > 0\}$ is not empty, Weak maximum principle to the operator $M$ with bounded coefficients (since $v \in C^{1}(\overline{U})$) will lead a contradiction that
            $$0 <   \max  _ {\{\overline{{u > 0}} \}} w = \max  _ {\partial \{u > 0 \}} w = \frac{0}{v} = 0$$
Hence $u \leq 0$ in $U$.
