## 一、引言
Transformer架构中的自注意力机制自提出以来，已成为自然语言处理和计算机视觉领域的核心构建模块。其通过计算序列中所有位置的成对相似度来捕获长距离依赖关系的能力，带来了显著性能提升。然而，标准的softmax注意力计算复杂度随序列长度呈二次增长，限制了其在长序列任务中的应用；同时，其在视觉任务中缺乏局部归纳偏置，且存在注意力坍塌等问题。近年来的研究表明，改进注意力机制是提升Transformer模型效率、性能和可解释性的关键路径。

现有研究主要从三个方向改进注意力机制：一是提升计算效率与稳定性，通过稀疏化、门控或遗忘机制减少冗余计算并缓解训练不稳定性；二是引入有效的归纳偏置，如局部性、能量显著性，以匹配特定领域的先验知识；三是探索注意力机制的统计学习理论，分析其过度拟合与泛化行为。尽管已有大量工作，但如何在不同任务中平衡性能、效率与可解释性，仍然是开放挑战。本文围绕Transformer注意力机制的改进与理论分析，系统梳理了11篇代表性论文，涵盖基础理论、高效架构和跨领域应用，旨在为研究者提供全面的视角。

## 二、方法分类
根据核心贡献与改进方向，这些论文可归为四类。第一类是**注意力机制的高效化设计**，旨在降低计算复杂度并提升模型对长序列的适配能力。例如，[2]提出无掩码注意力机制，[3]引入膨胀邻域注意力以扩大感受野，[5]通过遗忘门实现数据驱动的历史衰减，[10]将门控与稀疏注意力结合以兼顾稳定性和效率。第二类是**引入新的归纳偏置**，使注意力能更有效地捕捉输入的结构信息。[4]提出了能量门控注意力和小波位置编码，分别赋予注意力对令牌显著性和多尺度位置信息的感知能力。[8]则设计个性化注意力机制，利用电子健康记录引导视觉注意区域。第三类是**针对特定任务的改进**。[1]设计了一种基于自注意力引导的视觉解释方法，提升了ViT的可视化可解释性；[7]将Transformer注意力与神经过程核回归结合，在不失精度前提下实现亚二次复杂度；[9]则提出混合Transformer用于图像超分辨率，通过像素混合器增强局部性。第四类是**注意力机制的理论分析**。[6]从统计学习角度刻画了注意力在噪声标签分类场景下的良性过度拟合，[11]则通过研究LLM的注意力模式，提出无需微调即可提升长文本理解能力的序列注意优化方法。

## 三、论文详细分析
以下七篇为具有代表性的工作，逐一分析其核心贡献。Leem 和 Seo [1]针对Vision Transformer缺乏类似CNN的全局平均池化可视化方法之问题，提出了Attention Guided CAM。该方法利用自注意力图构造类特定响应，无需修改模型或额外训练，在ImageNet和PASCAL VOC上获得了优于同类方法的目标定位性能。

Lai 等人 [2]观察到基于掩码注意力的3D实例分割方法因初始掩码召回率低而收敛缓慢，设计了一种无掩码注意力的Transformer。通过引入中心回归作为辅助分支，并在交叉注意力中使用中心热图计算权重，该方法在ScanNet和S3DIS数据集上以更快的收敛速度达到了领先的分割精度。

Hassani 与 Shi [3]指出局部注意力缺乏对长距离依赖的有效建模，提出了膨胀邻域注意力（DiNA）。该机制在不显著增加计算量的情况下，通过逐步扩张关注范围实现了多尺度感受野。在ImageNet、ADE20K和COCO数据集上，DiNAT在分类、分割和检测任务中均优于Swin Transformer。

Zeris [4]从归纳偏置角度出发，认为标准注意力将令牌视作等显著性而忽略位置尺度。其提出的能量门控注意力根据端到端学习到的能量分数调整注意力权重，过滤低信息令牌；小波位置编码则在不同频率尺度提供位置信息，显著提升了ImageNet分类和机器翻译任务的性能。

Lin 等人 [5]借鉴循环神经网络中遗忘门的概念，为Transformer设计了一种数据依赖的遗忘机制。Forgetting Attention通过对未归一化的注意力分数加权衰减，使得模型能自适应地遗忘无关旧信息。FoX在长文本语言建模、长度外推和关键词检测任务上均超越了标准Transformer。

Sakamoto 与 Sato [6]从理论层面分析了注意力机制在带噪分类问题中的训练动态。通过定义信号-噪声比（SNR），他们严格证明了在标签噪声环境中，注意力会选择性地关注干净令牌，且随着噪声率升高，模型会出现良性过度拟合——即记忆噪声但不损害泛化。该研究首次从理论上解释了注意力的鲁棒性。

Gao 等人 [11]针对大语言模型的长文本理解能力不足，通过对LLM解码时注意力分布的深入分析，发现模型倾向于将大部分注意力集中于初始令牌。据此，他们提出了一种无需微调、仅通过修改注意力计算流程即可提升长文本性能的方法，在多种基准测试上效果显著。

**表：论文核心信息汇总**

| 序号 | 论文 | 年份 | 主要创新 | 数据集 | 关键结果 | 代码 |
|------|------|------|----------|--------|----------|------|
| 1 | [1] Attention Guided CAM | 2024 | 自注意力引导的CAM可视化方法 | ImageNet, PASCAL VOC | 定位性能优于CNN-CAM变体；无需重新训练 | 公开 |
| 2 | [2] Mask-Attention-Free Transformer | 2023 | 无掩码交叉注意力 + 中心回归辅助 | ScanNet, S3DIS | 收敛速度快2倍；AP/L优于基线 | 公开 |
| 3 | [3] Dilated Neighborhood Attention | 2022 | 膨胀邻域注意力（多尺度局部注意力） | ImageNet, ADE20K, COCO | 分类/分割/检测均优于Swin Transformer | 公开 |
| 4 | [4] Energy-Gated Attention & Wavelet Pos | 2026 | 能量门控 + 小波位置编码 | ImageNet, IWSLT14 | 分类Top-1提升1.5%；BLEU提升+0.8 | 未公开 |
| 5 | [5] Forgetting Transformer (FoX) | 2025 | 遗忘门控的Softmax注意力 | PG-19, Long-Bench | PPL降低；长文本外推优势 | 未公开 |
| 6 | [6] Token Selection Benign Overfitting | 2024 | 注意力训练的SNR理论分析 | 合成/带噪文本分类 | 证明注意力存在良性过度拟合 | 未公开 |
| 7 | [7] TNP-KR | 2024 | Transformer核回归神经过程 | 1D回归, 图像补全 | 复杂度O(n)优于O(n²)基线 | 未公开 |
| 8 | [8] Personalized Attention | 2022 | 电子病历引导的注意力权重调整 | 病理图像数据集 | 注意力图更符合病理专家标注 | 未公开 |
| 9 | [9] Efficient Mixed Transformer (EMT) | 2023 | 像素混合器增强局部性 + 混合Transformer | Set5, Set14, Urban100 | PSNR超过SwinIR；参数量降低30% | 未公开 |
| 10 | [10] Gated Sparse Attention (GSA) | 2026 | 门控融合稀疏注意力 | Long-Range Arena | 训练稳定；长序列速度提升3倍 | 未公开 |
| 11 | [11] Pay Attention to What You Need | 2023 | 无资源优化的长文本注意力改进 | LongBench, SCROLLS | 长序列理解提升10%；对短文本无影响 | 未公开 |

## 四、对比分析
从效率与效果的权衡来看，[5]、[10]和[7]代表了从不同角度优化复杂度的思路。[5]的遗忘门机制保留全注意力矩阵，但通过时间衰减降低早期令牌权重，在保持对短依赖建模能力的同时优化了长上下文性能，其优势在于结构简洁、无需稀疏掩码设计。[10]则是对稀疏注意力和门控机制的刚性结合，先通过稀疏选择过滤大量无关令牌，再以门控单元稳定训练，效率提升最为显著，但可能牺牲小部分精度。[7]通过将注意力矩阵近似为核回归过程，在复杂度上取得O(n)突破，但该方法专为函数回归设计，普适性有限。

在增强归纳偏置方面，[3]和[4]均致力于弥补标准注意力缺乏局部性的缺陷，但策略不同。[3]的膨胀邻域注意力通过在滑动窗口基础上引入膨胀因子，以层级方式扩大感受野，在保留局部稠密注意力的同时捕获全局信息，非常适合视觉任务。而[4]更进一步，利用小波变换显式地对不同频率成分施加位置约束，理论上更适用于图像和语音等多频信号，但工程实现复杂度较高。

针对应用场景，[1]和[8]都将注意力用于可解释性，但出发点不同。[1]致力于从预训练ViT中提取类激活图，属于事后解释；[8]则通过先验知识（病历）在训练阶段引导模型关注病理区域，属于任务驱动的注意力学习。[9]在超分辨率任务上同时引入像素混合器和通道注意力，实际上是通过结构模块设计隐式地补充了局部位置信息，避免了纯Transformer的高频细节丢失问题。

从理论研究看，[6]的观点——注意力在噪声环境下存在良性过度拟合——为理解注意力鲁棒性提供了基础支撑。该结论与[10]、[5]中观测到的训练稳定性现象存在一致性：门控或遗忘机制间接限制了噪声令牌的影响，从而稳定了注意力分布。

总体而言，多数优化方法牺牲了一定的通用性以适应特定场景或降低复杂度，而理论工作则为这些改进提供了坚实的数学依据。在视觉任务中，融合局部性先验（如[3]、[9]）仍是主要趋势；在语言任务中，如何高效处理超长序列（如[5]、[10]）是焦点所在。

## 五、未来展望
尽管现有工作已在多个维度推动了注意力机制的发展，但仍存在若干值得深入探索的方向。首先，当前的高效注意力方案多针对特定任务设计，缺乏通用的高效框架。未来应研究能够根据输入动态选择计算策略的自适应注意力，例如结合硬件感知的稀疏化与门控机制。其次，注意力输出的理论理解仍不完整。除泛化误差外，注意力头的交互行为、多头注意力的冗余性及其与模型容量的关系，有待系统性的理论建模。第三，跨模态与多模态注意力是重要增长点。如何像[8]那样将不同源信息自然融入注意力权重，同时保持低复杂度，将成为推动多模态学习的关键。最后，可解释性与效率之间的平衡需要进一步协调。在长序列或计算受限场景下，简化后的稀疏注意力往往掩盖了模型内部的决策逻辑；开发同时具备高效与高度可解释性的注意力变体，将对可靠AI应用产生深远影响。

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