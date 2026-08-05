Let $g, h$ be the inverse Fourier transforms of $\chi_U, \chi_{UK}$ (as given by the Plancherel theorem), and let $f = |U|^{-1}gh$. Then $f \in L^1$ and $\widehat{f} = \widehat{g} * \widehat{h}$ by Proposition (4.36); thus $\widehat{f}(\xi) = |U|^{-1} \int_U \chi_{UK} (\eta^{-1}\xi) d\eta$ has the desired properties.
(4.51) Theorem. If $N \subset \widehat{G}$ is closed, then $\nu(\iota(N)) = N$.
  Proof: If $\xi \notin N$, take $K = \{\xi\}$ and $W = \widehat{G} \setminus N$ in Lemma (4.50) to obtain $f \in \iota(N)$ such that $\widehat{f}(\xi) \neq 0$.
  When G is compact, the other half of the correspondence is easily analyzed. First, a simple lemma that will also be useful elsewhere.

(4.52) Lemma. If $f \in L^{1}(G)$ and $\xi \in \widehat{G}$ ($\subset L^{\infty}(G)$) then $f * \xi = \widehat{f}(\xi) \xi$.
  Proof: For any $x \in G$,
  $$f * \xi (x) = \int f (y) \langle y ^ {- 1} x, \xi \rangle d y = \langle x, \xi \rangle \int f (y) \overline{{\langle y , \xi \rangle}} d y = \widehat{f} (\xi) \langle x, \xi \rangle .$$
(4.53) Theorem. If $G$ is compact, then $\iota(\nu(\mathcal{I})) = \mathcal{I}$ for every closed ideal $\mathcal{I} \subset L^1(G)$.
  Proof: Since $G$ is compact, we have $\widehat{G} \subset L^{\infty} \subset L^{2} \subset L^{1}$ . Suppose $f \in \iota(\nu(\mathcal{I}))$ . Then $f * \xi = \widehat{f}(\xi) \xi$ by Lemma (4.52), and either $\widehat{f}(\xi) = 0$ or $\xi \notin \nu(\mathcal{I})$ . In the first case, $f * \xi = 0$ ; in the second case, there exists $g \in \mathcal{I}$ such that $\widehat{g}(\xi) = 1$ , so that $\xi = g * \xi \in \mathcal{I}$ by Lemma (4.52) again. In either case we have $f * \xi \in \mathcal{I}$ , and hence $f * g \in \mathcal{I}$ for any $g$ in the linear span of $\widehat{G}$ . The latter is dense in $L^{2}$ by Corollary (4.26), so $f * g \in \mathcal{I}$ for all $g \in L^{2}$ since $\mathcal{I}$ is closed. Finally, we can take $g$ to be an approximate identity to conclude that $f \in \mathcal{I}$ .
  When $G$ is noncompact, the question of whether $\iota(\nu(\mathcal{I})) = \mathcal{I}$ is much more delicate. We now exhibit a simple example to show that the answer can be negative.
(4.54) Theorem. Let $G = \mathbf{R}^n$ with $n \geq 3$, and let $S$ be the unit sphere in $\mathbf{R}^n$. There is a closed ideal $\mathcal{I}$ in $L^1(\mathbf{R}^n)$ such that $\nu(\mathcal{I}) = S$ but $\mathcal{I} \neq \iota(S)$.
  Proof: First we observe that if $f$ and $x_{1}f$ (= the function whose value at $x$ is $x_{1}f(x)$) are in $L^{1}(\mathbf{R}^{n})$ then
    $$\begin{array}{l} - 2 \pi i (x _ {1} f) ^ {\wedge} (\xi) = \int (- 2 \pi i x _ {1} e ^ {- 2 \pi i \xi \cdot x}) f (x) d x \\ = \int \frac{\partial e ^ {- 2 \pi i \xi \cdot x}}{\partial \xi_ {1}} f (x) d x = \frac{\partial \widehat{f}}{\partial \xi_ {1}} (\xi). \tag{4.55} \\ \end{array}$$
Hence $\partial \widehat{f} / \partial \xi_1$ exists and is continuous.

  Let $I$ be the set of all $f \in L^1$ such that $x_1 f \in L^1$ and $\widehat{f}|_{S} = (\partial \widehat{f} / \partial \xi_1)|_{S} = 0$, and let $\mathcal{I}$ be the closure of $I$ in $L^1$. Since $(L_y f)^\vee(\xi) =$
