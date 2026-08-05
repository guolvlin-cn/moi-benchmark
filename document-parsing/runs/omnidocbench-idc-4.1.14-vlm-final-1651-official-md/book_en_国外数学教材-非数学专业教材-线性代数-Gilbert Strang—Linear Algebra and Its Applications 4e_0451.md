  For linear programming, the important alternatives come when the constraints are inequalities. When is the feasible set empty (no x )?

    8J $Ax \geq b$ has a solution $x \geq 0$ or there is a $y \leq 0$ with $yA \geq 0$ and $yb < 0$.
Proof. The slack variables $w = Ax - b$ change $Ax \geq b$ into an equation. Use 8I:
        First alternative $\left[ \begin{array}{ll}A & -I \end{array} \right]\left[ \begin{array}{l}x\\ w \end{array} \right] = b$ for some $\left[ \begin{array}{l}x\\ w \end{array} \right]\geq 0.$
      Second alternative $y[A - I] \geq \left[ \begin{array}{ll}0 & 0 \end{array} \right]$ for some $y$ with $yb < 0$.
  It is this result that leads to a "nonconstructive proof" of the duality theorem.

## Problem Set 8.3

1. What is the dual of the following problem: Minimize $x_{1} + x_{2}$, subject to $x_{1} \geq 0$, $x_{2} \geq 0$, $2x_{1} \geq 4$, $x_{1} + 3x_{2} \geq 11$? Find the solution to both this problem and its dual, and verify that minimum equals maximum.
2. What is the dual of the following problem: Maximize $y_{2}$ subject to $y_{1} \geq 0$, $y_{2} \geq 0$, $y_{1} + y_{2} \leq 3$? Solve both this problem and its dual.
3. Suppose $A$ is the identity matrix (so that $m = n$), and the vectors $b$ and $c$ are nonnegative. Explain why $x^{*} = b$ is optimal in the minimum problem, find $y^{*}$ in the maximum problem, and verify that the two values are the same. If the first component of $b$ is negative, what are $x^{*}$ and $y^{*}$ ?
4. Construct a 1 by 1 example in which $Ax \geq b, x \geq 0$ is unfeasible, and the dual problem is unbounded.
5. Starting with the 2 by 2 matrix $A = \begin{bmatrix}1 & 0\\ 0 & -1\end{bmatrix}$, choose $b$ and $c$ so that both of the feasible sets $Ax \geq b$, $x \geq 0$ and $yA \leq c$, $y \geq 0$ are empty.
6. If all entries of A , b , and c are positive, show that both the primal and the dual are feasible.
7. Show that x = (1, 1, 1, 0) and y = (1, 1, 0, 1) are feasible in the primal and dual, with
          $$A = \left[ \begin{array}{\text{lll} l} 0 & 0 & 1 & 0 \\ 0 & 1 & 0 & 0 \\ 1 & 1 & 1 & 1 \\ 1 & 0 & 0 & 1 \end{array} \right], \qquad b = \left[ \begin{array}{l} 1 \\ 1 \\ 1 \\ 1 \end{array} \right], \qquad c = \left[ \begin{array}{l} 1 \\ 1 \\ 1 \\ 3 \end{array} \right].$$
  Then, after computing cx and yb , explain how you know they are optimal.
