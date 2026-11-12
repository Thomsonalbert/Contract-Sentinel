// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/// @title A beginner-friendly smart contract demonstrating core Solidity features
contract BasicsLearner {

    // ------------------------------------------------------------------------
    // 1. STATE VARIABLES (Stored permanently on the blockchain)
    // ------------------------------------------------------------------------
    
    address public owner;              // Stores the deployer's wallet address
    string public contractMessage;     // Public variables automatically get "getter" functions
    uint256 public totalDeposits;      // Unsigned integer (positive whole numbers)
    bool public isPaused;              // Boolean (true/false)

    // Struct: Create custom data types to group related variables
    struct User {
        string name;
        uint256 balance;
        bool isActive;
    }

    // Mapping: Key-value store (e.g., wallet address -> User struct data)
    mapping(address => User) public users;

    // ------------------------------------------------------------------------
    // 2. EVENTS (Used to notify off-chain applications/frontends)
    // ------------------------------------------------------------------------
    
    event DepositMade(address indexed account, uint256 amount);
    event MessageUpdated(string oldMessage, string newMessage);
    event UserRegistered(address indexed userAddress, string name);

    // ------------------------------------------------------------------------
    // 3. MODIFIERS (Custom function logic checks executed before/after functions)
    // ------------------------------------------------------------------------
    
    modifier onlyOwner() {
        // require checks if condition is true; if false, it reverts transaction and refunds leftover gas
        require(msg.sender == owner, "Only the owner can call this function");
        _; // Executes the actual function code here
    }

    modifier whenNotPaused() {
        require(!isPaused, "Contract is currently paused");
        _;
    }

    // ------------------------------------------------------------------------
    // 4. CONSTRUCTOR (Executes only ONCE when contract is deployed)
    // ------------------------------------------------------------------------
    
    constructor(string memory _initialMessage) {
        owner = msg.sender; // Set deployer as owner
        contractMessage = _initialMessage;
        isPaused = false;
    }

    // ------------------------------------------------------------------------
    // 5. FUNCTIONS
    // ------------------------------------------------------------------------

    /// @notice Register a user with a custom name
    function registerUser(string memory _name) public whenNotPaused {
        require(!users[msg.sender].isActive, "User already registered");

        // Save data to the mapping
        users[msg.sender] = User({
            name: _name,
            balance: 0,
            isActive: true
        });

        emit UserRegistered(msg.sender, _name);
    }

    /// @notice Deposit Native Crypto (ETH/Matic/Avax) into the contract
    /// @dev 'payable' modifier allows the function to receive cryptocurrency
    function deposit() public payable whenNotPaused {
        require(msg.value > 0, "Must send some ETH");
        require(users[msg.sender].isActive, "Must register before depositing");

        users[msg.sender].balance += msg.value;
        totalDeposits += msg.value;

        emit DepositMade(msg.sender, msg.value);
    }

    /// @notice Change the global contract message (Owner-only)
    function setMessage(string memory _newMessage) public onlyOwner {
        string memory oldMsg = contractMessage;
        contractMessage = _newMessage;

        emit MessageUpdated(oldMsg, _newMessage);
    }

    /// @notice Pause or unpause contract operations (Owner-only)
    function togglePause() public onlyOwner {
        isPaused = !isPaused;
    }

    /// @notice Read function: 'view' functions do NOT modify state and cost no gas when called off-chain
    function getUserBalance(address _user) public view returns (uint256) {
        return users[_user].balance;
    }

    /// @notice Read function: 'pure' functions do NOT read or modify any state on the blockchain
    function addNumbers(uint256 _a, uint256 _b) public pure returns (uint256) {
        return _a + _b;
    }
}