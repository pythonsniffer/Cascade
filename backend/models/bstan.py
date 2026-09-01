"""BSTAN — COPIED VERBATIM from Cascade_Integrated.ipynb cell A4.

Do not modify. The exported state_dicts are fit to exactly this architecture; any
change silently invalidates the validated results (Backend Instructions §11.3).
"""
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch_geometric.nn import GATConv


class BSTAN(nn.Module):
    def __init__(self, in_dim, gat_hidden=48, gru_hidden=48, heads=3, n_stations=35):
        super().__init__()
        self.N = n_stations
        self.gat1 = GATConv(in_dim, gat_hidden, heads=heads, concat=True,
                            edge_dim=1)  # edge_dim=1 -> buffer weights ENTER attention
        self.gru = nn.GRU(gat_hidden * heads, gru_hidden, batch_first=True)  # Eq. 9-12
        self.mlp = nn.Sequential(nn.Linear(gru_hidden, 32), nn.ReLU(), nn.Linear(32, 2))

    def spatial(self, x, ei, ew):
        # single GAT hop: 2 layers over-smooth a serial line and wash out the spike
        return F.elu(self.gat1(x, ei, edge_attr=ew))

    def forward(self, x_window, ei, ew):
        T = x_window.shape[0]
        emb = torch.stack([self.spatial(x_window[t], ei, ew) for t in range(T)])  # [T,N,H]
        emb = emb.permute(1, 0, 2)                   # [N,T,H]
        out, _ = self.gru(emb)                       # [N,T,gru_hidden]
        return self.mlp(out[:, -1, :])               # [N,2]
