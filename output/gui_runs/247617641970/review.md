## 一、引言
Transformer架构自提出以来，凭借其强大的序列建模能力，迅速成为自然语言处理与计算机视觉领域的主流模型。其核心组件——自注意力（Self-Attention）机制，通过计算序列中所有位置之间的成对相似度来捕获长距离依赖关系，为模型性能的飞跃提供了关键支撑。然而，随着应用场景的不断拓展，标准注意力机制面临的挑战也日益凸显：其二次计算复杂度限制了在长序列和高分辨率图像上的应用；其固有的全局均匀关注模式缺乏针对重要区域的偏置，可能导致计算资源的浪费或对噪声的过度敏感；此外，在3D点云、图像超分辨率等特定任务中，如何将注意力机制与数据固有的局部性或结构先验有效结合，仍是亟待解决的问题。

本文聚焦于近期为应对上述挑战而提出的Transformer注意力机制改进工作，涵盖视觉解释（Visual Explanations）、3D实例分割（3D Instance Segmentation）、图像超分辨率（Image Super-Resolution）、长上下文语言建模（Long-Context Language Modeling）以及理论分析（Theoretical Analysis）等多个方向。我们将这些工作按方法范式和解决的问题进行归类分析：包括通过引入遗忘门（Forget Gate）、能量门控（Energy Gate）等机制增强注意力可塑性（Plasticity）；通过局部化（Localized）或稀疏化（Sparse）策略降低计算复杂度；以及通过可视化（Visualization）方法提升模型可解释性。通过对11篇代表性论文的深入剖析，本文旨在揭示当前注意力机制优化路径的内在逻辑、性能权衡与未来趋势。

## 二、方法分类
首先，一部分工作旨在通过引入额外门控或偏置信号，改进标准缩放点积注意力的信息流与稳定性。例如，[5]提出的Forgetting Attention通过引入类似于递归模型中遗忘门的数据依赖权重，在长上下文中实现对不相关历史信息的动态衰减。[4]则提出了能量门控注意力（Energy-Gated Attention），通过端到端学习每个token的“信息能量”作为偏置，引导模型关注高信息密度区域，并配合小波位置编码（Wavelet Positional Encoding）实现频率感知的局部性偏置。[10]的Gated Sparse Attention（GSA）将稀疏注意力与门控机制结合，旨在同时实现计算效率的提升和训练稳定性的增强。

其次，针对注意力二次复杂度在视觉任务中带来的计算开销，一系列工作探索了局部化或稀疏化的注意力模式。[3]提出的Dilated Neighborhood Attention（DiNA）是对局部邻域注意力（Neighborhood Attention）的扩展，通过引入空洞（Dilation）概念，在不显著增加计算量的前提下扩大感受野。[9]则提出了Efficient Mixed Transformer（EMT），在混合Transformer块中部分替换标准注意力为像素混合器（Pixel Mixer，一种局部操作），以增强模型对局部纹理的捕捉能力，同时降低整体复杂度。[2]针对3D实例分割，发现传统的掩码注意力（Mask-Attention）因初始掩码低召回率导致收敛缓慢，因此提出完全放弃该设计，转而采用辅助中心回归（Auxiliary Center Regression）来引导查询（Query）学习。

另一类研究聚焦于通过可视化方法理解或归因ViT的决策依据。[1]提出的Attention Guided CAM（AG-CAM）利用自注意力层的注意力图（Attention Map）来指导类激活映射（CAM）的生成，从而在ViT中生成定位更精准的可视化热力图。[8]则将注意力机制与临床记录相结合，提出了一种个性化注意力机制，使模型在分析医学图像时能够根据患者临床信息动态调整关注区域。最后，[6]和[7]从理论或应用建模角度进行了探索。[6]从理论上分析了注意力机制在含噪标签分类任务中学习token选择的动力学过程，揭示了良性过拟合（Benign Overfitting）现象。[7]则将Transformer注意力与神经过程（Neural Processes）结合，提出TNP-KR，通过核回归（Kernel Regression）近似来克服传统注意力在神经过程中带来的二次复杂度瓶颈。[11]则侧重于已经训练好的大语言模型（LLM），通过分析其注意力模式提出了一种无需微调的推理时后处理方法，以提升模型的长文本理解能力。

## 三、论文详细分析
[1] Leem等人在2024年提出Attention Guided CAM（AG-CAM），旨在解决ViT缺乏类似CNN中基于梯度的可视化工具的问题。核心创新在于利用ViT自身的自注意力图来引导类激活映射的生成，具体做法是聚合多层注意力头信息以形成高质量的定位先验。该方法是即插即用的，无需重新训练。实验在ImageNet等数据集上进行，与Rollout、Grad-CAM等方法相比，在弱监督语义分割任务上取得了更高的mIoU（平均交并比）。代码已开源。

[2] Lai等人2023年提出的Mask-Attention-Free Transformer专注于3D实例分割。作者观察到基于掩码注意力的Transformer方法因初始掩码质量差而收敛缓慢。创新性地抛弃了掩码注意力，转而让对象查询（Object Queries）通过一个辅助的中心回归头来学习空间位置先验，从而直接与点云特征进行交互。该方法在ScanNet、S3DIS等3D分割基准上取得了具有竞争力的精度，同时显著加速了训练收敛速度，并降低了内存占用。

[3] Hassani和Shi在2022年提出Dilated Neighborhood Attention Transformer（DiNAT）。其核心创新在于将空洞卷积的思想引入局部注意力机制，在邻域注意力的基础上，通过空洞因子控制被关注的邻域令牌间的步长，从而在不增加计算和参数量（保持邻域大小不变）的情况下，指数级地扩大感受野。在ImageNet分类、ADE20K语义分割、COCO目标检测等多个视觉任务上，DiNAT超越了基于滑动窗口的Swin Transformer和原始的NA（Neighborhood Attention）模型。

[4] Zeris的工作（2026年）从偏置引入的角度改进注意力。其创新包括：能量门控（Energy Gate），为每个token学习一个标量能量值，通过Sigmoid函数将软注意力权重乘以此能量值，实现数据驱动的显著性筛选；以及小波位置编码（Wavelet Position Encoding），使用不同尺度的小波基函数分解得到的频率和位置信息，为注意力提供显式的多尺度位置先验。尽管是针对理论的实验性工作，但该工作在合成序列长程建模和部分语言建模指标上验证了其稳定性和性能提升潜力。

[5] Lin等人2025年提出的Forgetting Transformer（FoX）是核心创新之一。他们发现标准Softmax注意力的“衰减”效果有限，因此引入了一个可学习的遗忘门（Forget Gate），作用于softmax之前的注意力logits值，根据查询和键的信息，对历史信息的未归一化分数进行数据依赖的“遗忘”。这种机制使得模型在长文本中能更有效地丢弃无关上下文。语言建模评估（如PG-19、Long Range Arena）表明，FoX在困惑度上优于同等规模的Transformer和线性注意力模型，同时具备更好的长度外推能力。

[6] Sakamoto和Sato在2024年的理论工作中，分析了单层注意力机制在二元token选择分类任务上的训练动态。他们证明，在标签噪声存在的情况下，注意力机制不会过拟合噪声样本，而是展现出良性过拟合（Benign Overfitting）行为：模型会学习到信号比（SNR）更高的“核心”token，而噪声token的影响力被抑制。这一结论为注意力机制在噪声环境下的鲁棒性提供了理论支撑。

[7] Jenson等人2024年的TNP-KR针对神经过程（NP）中的注意力瓶颈。标准NP使用Transformer注意力会导致\(O(n^2)\)复杂度，限制了其在大数据集上的应用。TNP-KR的核心是将注意力重新解释为核回归（Kernel Regression）过程，并利用随机特征近似（如正随机特征近似）来线性化核，从而将复杂度降至\(O(n)\)。在一维函数回归和图像完成等任务上，TNP-KR的预测性能与最先进的NP模型相当，但具有更高的可扩展性。

[8] Takagi等人2022年提出了针对医学图像的个性化注意力。其创新点在于设计了一个融合多重实例学习（MIL）与Transformer的架构。输入的临床记录文本（如患者年龄、病史）通过一个编码器生成一个“个性化向量”，该向量被用作查询，与从病理图像中提取的斑块特征进行计算，从而生成受额外临床信息指导的注意力权重。在弥散性大B细胞淋巴瘤（DLBCL）数据集上的实验中，该模型能够定位出与临床预后相关的特定图像区域。

[9] Zheng等人2023年提出Efficient Mixed Transformer（EMT）用于单图像超分辨率。其创新在于Mixer Transformer Block（MTB），该块由多个Transformer层堆叠，但部分层将标准注意力替换为像素混合器（Pixel Mixer），这是一种轻量级的逐通道、逐空间位置的局部信息混合操作。这种混合设计在保持全局依赖建模能力的同时，增强了局部纹理细节的恢复。在Set5、Set14、B100、Urban100等基准测试上，EMT以更少的FLOPs取得了与SwinIR等先进方法相当或更优的PSNR/SSIM指标。

[10] Shen和Shen在2026年的工作中提出Gated Sparse Attention（GSA）。GSA的核心是整合稀疏注意力的计算效率和门控机制的训练稳定性。它首先通过一种高效的稀疏模式（如基于Top-K的稀疏或固定模式）降低注意力矩阵的计算量，然后在该稀疏结果上应用一个可学习的门控函数，该门控会根据上下文动态调整稀疏注意力输出的权重，以抑制噪声并缓解注意力汇聚（Attention Sink）现象。实验在多种长度的语言混合基准上显示，GSA在长上下文任务上的表现优于独立的稀疏或门控基线模型。

[11] Gao等人2023年的工作则属于模型推理时优化的范畴。他们观察到，LLM处理长文本时，注意力权重往往在无意义的token（如分隔符、代词）上产生高注意力，浪费了模型容量。为此，他们提出了一种无需额外训练或参数的方法，即在推理时，根据预先计算或实时统计的token重要性（例如，通过忽略注意力图中对后续层贡献极小的token），对注意力结果进行修剪或重加权。实验表明，该方法能有效提升GPT等模型在长文本问答和摘要任务上的准确率。

| 序号 | 论文 | 年份 | 主要创新 | 数据集 | 关键结果 | 代码 |
|:---:|:---|:---:|:---|:---|:---|:---|
| 1 | Attention Guided CAM: ... | 2024 | 利用自注意力图引导ViT的CAM生成 | ImageNet | 在弱监督语义分割中mIoU优于Rollout、Grad-CAM等方法 | 开源 |
| 2 | Mask-Attention-Free Transformer ... | 2023 | 抛弃掩码注意力，采用辅助中心回归引导查询 | ScanNet, S3DIS | 加速收敛，精度与现有SOTA相当，内存更优 | 开源 |
| 3 | Dilated Neighborhood Attention ... | 2022 | 在邻域注意力中引入空洞，指数级扩大感受野 | ImageNet, ADE20K, COCO | 分类、分割、检测任务性能超越Swin Transformer | 开源 |
| 4 | Energy-Gated Attention ... | 2026 | 能量门控筛选显著性token，小波位置编码提供多尺度先验 | 合成序列及语言建模 | 在长程依赖任务上提升稳定性与性能 | 未提及 |
| 5 | Forgetting Transformer: ... | 2025 | 在注意力中引入数据依赖的遗忘门，实现动态长程遗忘 | PG-19, Long Range Arena | 困惑度优于同等大小Transformer，长度外推能力强 | 未提及 |
| 6 | Benign Overfitting in Token Selection ... | 2024 | 理论证明注意力机制在含噪分类中的良性过拟合行为 | 合成数据集 | 模型学习高信噪比核心token，抑制噪声token | 未提及 |
| 7 | Transformer Neural Processes - Kernel Regression | 2024 | 将NP中的注意力核回归化，利用随机特征将复杂度降至O(n) | 一维函数回归，图像完成 | 性能与SOTA NP相当，计算效率显著提升 | 未提及 |
| 8 | Transformer-based Personalized Attention ... | 2022 | 使用编码后的临床记录作为查询，指导医学图像注意力的个性化生成 | DLBCL病理数据集 | 能定位与临床预后相关的区域 | 未提及 |
| 9 | Efficient Mixed Transformer ... | 2023 | 混合Transformer块，部分层用像素混合器替代注意力增强局部性 | Set5, Set14, B100, Urban100 | 以更低FLOPs取得与SwinIR相当的PSNR/SSIM | 未提及 |
| 10 | Gated Sparse Attention: ... | 2026 | 整合稀疏注意力的效率与门控机制的训练稳定性及抗注意力汇聚能力 | 长上下文语言混合基准 | 优于独立的稀疏或门控基线 | 未提及 |
| 11 | Pay Attention to What You Need | 2023 | 利用推理时token重要性统计，对注意力进行无需训练的重加权 | 长文本问答、摘要 | 有效提升LLM长文本任务准确率 | 未提及 |

## 四、对比分析
上述工作从不同角度对Transformer注意力机制进行了优化，各具优劣与适用场景。从增强可塑性角度看，FoX [5]和GSA [10]均引入了门控机制，但目标不同：FoX侧重于对历史信息进行选择性遗忘，尤其适用于无限长的上下文建模；而GSA侧重于在稀疏化条件下保持稳定的训练动态，更偏向于在有限预算下处理极长输入。二者的潜在劣势在于引入了额外参数，且可能在某些任务上（如视觉，GSA的工作背景主要是语言）需要特定的超参数调优。相比之下，AG-CAM [1]和[11]则完全不需要修改模型或训练过程，前者服务于模型解释，后者服务于推理加速，二者计算友好，是高效的后处理工具，但性能增益受限于原始模型的表达能力。

在降低复杂性方面，DiNAT [3]和EMT [9]都针对视觉Transformer的局部性问题，但路径不同。DiNAT通过扩大感受野来捕获更广的上下文，适合需要大范围依赖的任务（如大物体分割）；EMT则通过混合局部与全局操作来增强纹理细节，更适合图像超分辨率这类对精细结构敏感的任务。TNP-KR [7]和GSA [10]均旨在降低注意力在推理时的二次复杂度，但分别应用于神经过程和语言模型，其依赖的基础假设（如对核函数的近似）不同，因此不能直接对比。

在理论基础方面，[6]提供了理解注意力泛化行为的严谨框架，是少数从理论角度解释“注意力为何奏效”的工作，但其结论建立在简化的模型设置上（单层注意力），对复杂真实模型的推广尚待验证。相比之下，[4]的贡献也是偏原则性的，它将偏置引入与频谱分析结合，其方法在生物实在性上有启发意义，但目前主要停留在概念验证和合成任务上。在应用落地层面，[2]和[8]都针对特定领域（3D点云、病理图像）提出了任务驱动的高效解决方案，它们对领域先验的利用十分充分（如3D点云的稀疏性和病理图像的临床背景），但在迁移到其他领域时会面临挑战。

## 五、未来展望
综合现有工作，Transformer注意力机制的改进仍有大量研究空白。首先，门控与动态衰减机制（如FoX [5]）的泛化性验证不足，目前主要集中在语言建模领域，其在多模态、视觉任务中的有效性尚待探索。未来可以考虑设计一种通用的“自适应遗忘”框架，使其能够根据不同模态（如文本、图像、点云）的统计特性自动调整遗忘策略。

其次，基于核方法的低复杂度注意力（如[7]）具备巨大的潜力，但现有方法常依赖于随机特征的选取，其近似精度和训练稳定性仍然是一个挑战。将更灵活的核学习方法（如深度核学习）与高效的注意力近似相结合，可能是通往兼顾精度与效率的道路。

第三，目前对注意力机制的绝大多数理论分析（如[6]）仍局限于浅层或线性化模型。深入分析多层、多头注意力在复杂任务（如组合推理）中的学习动态和泛化边界，是支撑未来模型设计的关键理论需求。

最后，模型可解释性（如[1]）与高效推理（如[10], [11]）的结合是一个富有前景但未被充分探索的方向。例如，是否可以设计一个内置可解释性的稀疏注意力模块，使其不仅计算高效，还能同时输出人类可理解的决策归因图？此外，针对特定领域（如医学、自动驾驶），如何将领域知识（如解剖学结构、物理规律）作为硬偏置（Hard Inductive Bias）正式地编码进注意力机制（而不仅仅是作为软提示，如[8]），也是一个充满挑战的研究前沿。

## 参考文献

[1] Saebom Leem, Hyunseok Seo. **Attention Guided CAM: Visual Explanations of Vision Transformer Guided by Self-Attention**. (2024). arXiv: [2402.04563v1](http://arxiv.org/abs/2402.04563v1). [[代码]](https://github.com/LeemSaebom/Attention-Guided-CAM-Visual-Explanations-of-Vision-Transformer-Guided-by-Self-Attention)
[2] Xin Lai, Yuhui Yuan, Ruihang Chu 等. **Mask-Attention-Free Transformer for 3D Instance Segmentation**. (2023). arXiv: [2309.01692v1](http://arxiv.org/abs/2309.01692v1). [[代码]](https://github.com/JIA-Lab-research/Mask-Attention-Free-Transformer)
[3] Ali Hassani, Humphrey Shi. **Dilated Neighborhood Attention Transformer**. (2022). arXiv: [2209.15001v3](http://arxiv.org/abs/2209.15001v3). [[代码]](https://github.com/SHI-Labs/Neighborhood-Attention-Transformer)
[4] Athanasios Zeris. **Energy-Gated Attention and Wavelet Positional Encoding: Complementary Inductive Biases for Transformer Attention**. (2026). arXiv: [2605.26355v1](http://arxiv.org/abs/2605.26355v1).
[5] Zhixuan Lin, Evgenii Nikishin, Xu Owen He 等. **Forgetting Transformer: Softmax Attention with a Forget Gate**. (2025). arXiv: [2503.02130v2](http://arxiv.org/abs/2503.02130v2).
[6] Keitaro Sakamoto, Issei Sato. **Benign Overfitting in Token Selection of Attention Mechanism**. (2024). arXiv: [2409.17625v3](http://arxiv.org/abs/2409.17625v3).
[7] Daniel Jenson, Jhonathan Navott, Mengyan Zhang 等. **Transformer Neural Processes - Kernel Regression**. (2024). arXiv: [2411.12502v4](http://arxiv.org/abs/2411.12502v4).
[8] Yusuke Takagi, Noriaki Hashimoto, Hiroki Masuda 等. **Transformer-based Personalized Attention Mechanism for Medical Images with Clinical Records**. (2022). arXiv: [2206.03003v2](http://arxiv.org/abs/2206.03003v2).
[9] Ling Zheng, Jinchen Zhu, Jinpeng Shi 等. **Efficient Mixed Transformer for Single Image Super-Resolution**. (2023). arXiv: [2305.11403v5](http://arxiv.org/abs/2305.11403v5).
[10] Alfred Shen, Aaron Shen. **Gated Sparse Attention: Combining Computational Efficiency with Training Stability for Long-Context Language Models**. (2026). arXiv: [2601.15305v1](http://arxiv.org/abs/2601.15305v1).
[11] Yifei Gao, Shaohong Chen, Lei Wang 等. **Pay Attention to What You Need**. (2023). arXiv: [2307.13365v3](http://arxiv.org/abs/2307.13365v3).