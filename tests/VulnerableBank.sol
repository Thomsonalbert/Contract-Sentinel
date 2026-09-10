// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

contract VulnerableBank {
    mapping(address => uint256) public balances;

    function deposit() public payable {
        balances[msg.sender] += msg.value;
    }

    function withdraw() public {
        uint256 amount = balances[msg.sender];

        (bool success, ) = msg.sender.call{value: amount}("");

        require(success);

        balances[msg.sender] = 0;
    }
}