// nodeTypes.jsx
import React from 'react'
import NodeRankDetails from './NodeRankDetails'

// Вариант 2: "function" без стрелки
export function makeNodeTypes(onChangeNode, onDeleteRank) {
  return {
    rankNode: function rankNode(nodeProps) {
      return (
        <NodeRankDetails
          {...nodeProps}
          onChangeNode={onChangeNode}
          onDeleteRank={onDeleteRank}
        />
      )
    }
  }
}

