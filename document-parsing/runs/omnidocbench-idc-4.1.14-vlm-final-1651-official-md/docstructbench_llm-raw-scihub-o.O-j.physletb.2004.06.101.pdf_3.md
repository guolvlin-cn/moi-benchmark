  For consistency, the time derivative of the constraints of (10) must vanish and hence they must have vanishing Poisson bracket with H . Using the fundamental Poisson brackets

    $$\left[ U (x), \Pi^ {U} (y) \right] = \delta (x - y), \tag{13}$$
etc., we find that the primary constraints of (10) imply the secondary constraints

    $$\left(\Sigma , \Sigma_ {i}\right) = \left(- \partial_ {k} \Pi_ {k} ^ {V}, \varepsilon^ {i j k} \partial_ {j} \left(\Pi_ {k} ^ {B} - m V _ {k}\right) - \mu^ {2} B _ {i}\right). \tag{14}$$
  If $\mu^2 = 0$ (the Cremmer-Scherk model Lagrangian [1]), the constraints of (14) would become reducible as then $\partial_i\Sigma_i = 0$ and only the transverse portions of $\Sigma_{i}$ are constraints. Furthermore, with $\mu^2 \neq 0$, the requirement $\dot{\Sigma}_i = 0$ leads to a tertiary constraint
    $$T _ {k} \equiv \mu^ {2} \Pi_ {k} ^ {B} = 0 \tag{15}$$
with $\Sigma_{i}$ and $T_{k}$ constituting second class constraints as
    $$\left[ T _ {k} (x), \Sigma_ {i} (y) \right] = \mu^ {4} \delta_ {i k} \delta (x - y). \tag{16}$$
  All other constraints are first class and no further constraints need to be imposed for consistency. There are consequently five first class constraints ($\Phi^U$, $\Phi_k^A$ and $\Sigma$) and six second class constraints ($\Sigma_{i}$ and $T_{k}$). The constraints $\Phi^U$ and $\boldsymbol{\Sigma}$ correspond to the usual gauge transformations $\delta W_0 = \partial_0\Omega$, $\delta W_{i} = \partial_{i}\Omega$ associated with a gauge field $W_{\mu}$, while $\Phi_k^A$ is associated with the fact that in (12) $A_{k}$ acts merely as a Lagrange multiplier (i.e., it is not dynamical) and hence its value is completely arbitrary. Suitable gauge conditions associated with the first class constraints are
    $$\left(\gamma^ {U}, \gamma_ {k} ^ {A}, \gamma^ {V}\right) = (U, A _ {k}, \partial_ {k} V _ {k}) = 0. \tag{17}$$
From (10), (14), (15) and (17) it is evident that the only dynamical degrees of freedom are

    $$V _ {i} ^ {T} \equiv \left(\delta_ {i j} - \partial_ {i} \partial_ {j} / \partial^ {2}\right) V _ {j}. \tag{18}$$
  We can verify this directly by explicitly eliminating the non-physical degrees of freedom in (4). First, one decomposes $V_{k}$ , $A_{k}$ and $B_{k}$ into transverse ($T$) and longitudinal ($L$) parts where
    $$\nabla \times \mathbf{V} ^ {L} \equiv 0 \equiv \nabla \cdot \mathbf{V} ^ {T}, \tag{19}$$
etc., (4) now becomes

    $$\begin{array}{l} 2 L = \left(\dot{\mathbf{B}} ^ {L}\right) ^ {2} - \left(\nabla \cdot \mathbf{B} ^ {L}\right) ^ {2} + \left[ \dot{\mathbf{B}} ^ {T} - \nabla \times \mathbf{A} ^ {T} \right] ^ {2} + \left(\dot{\mathbf{V}} ^ {T}\right) ^ {2} - \left(\nabla \times \mathbf{V} ^ {T}\right) ^ {2} + \left[ \dot{\mathbf{V}} ^ {L} - \nabla U \right] ^ {2} \\ + 2 m \left[ \mathbf{V} ^ {T} \cdot (\nabla \times \mathbf{A} ^ {T}) + \mathbf{B} ^ {L} \cdot \dot{\mathbf{V}} ^ {L} + \mathbf{B} ^ {T} \cdot \dot{\mathbf{V}} ^ {T} - \mathbf{B} ^ {L} \cdot \nabla U \right] + 2 \mu^ {2} \left[ \mathbf{A} ^ {T} \cdot \mathbf{B} ^ {T} + \mathbf{A} ^ {L} \cdot \mathbf{B} ^ {L} \right]. \tag{20} \\ \end{array}$$
The equations of motion for $\mathbf{A}^L$ and $U$, respectively, imply that
    $$\mathbf{B} ^ {L} = 0 = \dot{\mathbf{V}} ^ {L} - \nabla U, \tag{21}$$
reducing (20) to

    $$2 L = \left(\dot{\mathbf{V}} ^ {T}\right) ^ {2} - \left(\nabla \times \mathbf{V} ^ {T}\right) ^ {2} + \left[ \dot{\mathbf{B}} ^ {T} - \nabla \times \mathbf{A} ^ {T} \right] ^ {2} + 2 m \mathbf{V} ^ {T} \cdot \left(\nabla \times \mathbf{A} ^ {T}\right) + 2 m \mathbf{B} ^ {T} \cdot \dot{\mathbf{V}} ^ {T} + 2 \mu^ {2} \mathbf{A} ^ {T} \cdot \mathbf{B} ^ {T}. \tag{22}$$
Since

    $$\mathbf{A} ^ {T} \cdot \mathbf{B} ^ {T} = - (\nabla \times \mathbf{A} ^ {T}) \cdot (\nabla^ {2}) ^ {- 1} (\nabla \times \mathbf{B} ^ {T}), \tag{23}$$
we can eliminate $\nabla \times \mathbf{A}^T$ from (22) to obtain
    $$\nabla \times \mathbf{A} ^ {T} = \dot{\mathbf{B}} ^ {T} - m \mathbf{V} ^ {T} + \mu^ {2} (\nabla^ {2}) ^ {- 1} (\nabla \times \mathbf{B} ^ {T}). \tag{24}$$
